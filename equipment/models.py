"""
Equipment / tools register.

Unlike procurement items (quantity-based catalogue entries), every tool here is ONE physical unit with its own code (EQ-0001 ...),
its own condition, its own current location (a warehouse or a project) and its own history:

    Tool            the physical unit
    ToolTransfer    a movement request: site engineer asks -> a manager approves -> the storekeeper completes it
                    (completed rows are the movement history; the opening "received into the warehouse" is one too)
    ToolMaintenance a repair / service job on a tool (opened by the storekeeper, usually when a tool comes back from a project)

Location rule: a tool is either in a Warehouse or on a Project, never both; a tool in transit is still at its old location until
the storekeeper completes the transfer.
"""
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

CODE_PREFIX = 'EQ-'


class Tool(models.Model):
    STATUS_NEW = 'new'
    STATUS_WORKING = 'working'
    STATUS_NEEDS_MAINTENANCE = 'needs_maintenance'
    STATUS_IN_MAINTENANCE = 'in_maintenance'
    STATUS_BROKEN = 'broken'
    STATUS_SCRAPPED = 'scrapped'
    STATUS_CHOICES = (
        (STATUS_NEW, _('New')),
        (STATUS_WORKING, _('Working')),
        (STATUS_NEEDS_MAINTENANCE, _('Needs maintenance')),
        (STATUS_IN_MAINTENANCE, _('In maintenance')),
        (STATUS_BROKEN, _('Broken')),
        (STATUS_SCRAPPED, _('Scrapped')),
    )
    # statuses in which the tool can be handed to a project
    AVAILABLE_STATUSES = (STATUS_NEW, STATUS_WORKING)

    code = models.CharField(max_length=20, unique=True, blank=True, editable=False, help_text=_('Printed on the tool label, e.g. EQ-0001 (assigned automatically)'))
    name = models.CharField(max_length=150, help_text=_('Tool name'))
    category = models.CharField(max_length=60, blank=True, help_text=_('e.g. Grinder, Drill, Ladder, Vibrator'))
    manufacturer = models.CharField(max_length=100, blank=True)
    model_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WORKING)
    warehouse = models.ForeignKey('procurement.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='tools')
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='tools')
    holder = models.CharField(max_length=100, blank=True, help_text=_('Person who has the tool on site'))
    photo = models.ImageField(upload_to='equipment/tools/', null=True, blank=True)
    notes = models.TextField(blank=True)
    source_ref = models.CharField(max_length=40, blank=True, db_index=True, editable=False, help_text=_('Where the record was imported from (makes the import safe to repeat)'))
    last_inventory_date = models.DateField(null=True, blank=True, help_text=_('Last time the tool was seen in a stock-take'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.name}'

    # ---------------------------------------------------------------- code
    @classmethod
    def next_code(cls):
        last = cls.objects.order_by('-id').values_list('code', flat=True).first()
        number = 0
        if last and last.startswith(CODE_PREFIX):
            try:
                number = int(last[len(CODE_PREFIX):])
            except ValueError:
                number = cls.objects.count()
        return f'{CODE_PREFIX}{number + 1:04d}'

    def save(self, *args, **kwargs):
        if not self.code:
            with transaction.atomic():
                self.code = self.next_code()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    # ---------------------------------------------------------------- location
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.warehouse_id and self.project_id:
            raise ValidationError(_('A tool is either in a warehouse or on a project, not both.'))

    @property
    def location_label(self):
        if self.project_id:
            return f'{self.project.project_symbol} - {self.project.name}'
        if self.warehouse_id:
            return self.warehouse.name
        return '-'

    @property
    def is_available(self):
        return self.status in self.AVAILABLE_STATUSES and not self.pending_transfer()

    def pending_transfer(self):
        return self.transfers.filter(status__in=(ToolTransfer.REQUESTED, ToolTransfer.APPROVED)).first()

    def open_maintenance(self):
        return self.maintenance_jobs.filter(status__in=(ToolMaintenance.OPEN, ToolMaintenance.IN_PROGRESS)).first()


class ToolTransfer(models.Model):
    """A request to move a tool between locations, and (once completed) the record that it moved."""

    REQUESTED = 'requested'
    APPROVED = 'approved'
    COMPLETED = 'completed'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (REQUESTED, _('Requested')), (APPROVED, _('Approved')), (COMPLETED, _('Completed')),
        (REJECTED, _('Rejected')), (CANCELLED, _('Cancelled')),
    )

    KIND_OPENING = 'opening'      # first entry of the tool into a warehouse
    KIND_ISSUE = 'issue'          # warehouse -> project
    KIND_RETURN = 'return'        # project -> warehouse
    KIND_TRANSFER = 'transfer'    # project -> project, warehouse -> warehouse
    KIND_CHOICES = ((KIND_OPENING, _('Received')), (KIND_ISSUE, _('Issued to project')), (KIND_RETURN, _('Returned')), (KIND_TRANSFER, _('Transferred')))

    CONDITION_OK = 'ok'
    CONDITION_MAINTENANCE = 'needs_maintenance'
    CONDITION_SCRAP = 'scrap'
    CONDITION_CHOICES = ((CONDITION_OK, _('Good')), (CONDITION_MAINTENANCE, _('Needs maintenance')), (CONDITION_SCRAP, _('Scrap')))

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='transfers')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_TRANSFER)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=REQUESTED)

    from_warehouse = models.ForeignKey('procurement.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    from_project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    to_warehouse = models.ForeignKey('procurement.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    to_project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    holder = models.CharField(max_length=100, blank=True, help_text=_('Person receiving the tool on site'))
    note = models.TextField(blank=True)

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    requested_at = models.DateTimeField(default=timezone.now)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    completed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True)

    # filled by the storekeeper when the tool comes back from a project
    return_condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, blank=True)
    return_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-requested_at', '-id']

    def __str__(self):
        return f'{self.tool.code}: {self.from_label} -> {self.to_label} ({self.get_status_display()})'

    @staticmethod
    def _label(warehouse, project):
        if project:
            return f'{project.project_symbol}'
        if warehouse:
            return warehouse.name
        return '-'

    @property
    def from_label(self):
        return self._label(self.from_warehouse, self.from_project)

    @property
    def to_label(self):
        return self._label(self.to_warehouse, self.to_project)


class ToolMaintenance(models.Model):
    OPEN = 'open'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'
    SCRAPPED = 'scrapped'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = ((OPEN, _('Open')), (IN_PROGRESS, _('In progress')), (DONE, _('Done')), (SCRAPPED, _('Scrapped')), (CANCELLED, _('Cancelled')))

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='maintenance_jobs')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=OPEN)
    problem = models.TextField(help_text=_('What is wrong / what service is needed (e.g. needs a new motor and carbon brushes)'))
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    opened_at = models.DateTimeField(default=timezone.now)
    vendor = models.CharField(max_length=150, blank=True, help_text=_('Workshop / supplier doing the repair'))
    parts = models.CharField(max_length=300, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    started_date = models.DateField(null=True, blank=True)
    finished_date = models.DateField(null=True, blank=True)
    result_note = models.CharField(max_length=300, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-opened_at', '-id']

    def __str__(self):
        return f'{self.tool.code} maintenance ({self.get_status_display()})'
