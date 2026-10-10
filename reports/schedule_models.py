"""
Imported CPM schedule (Microsoft Project / Primavera) for a project.

The reference "Internal Monthly Report" template this app's internal
report is modeled on has a "CRITICAL PATH" section whose own instructions
say: "Extract from Primavera or MS Project and Include as Attachment to
Report (Only Include here Key Activities on Critical Path)" -- i.e. real
EPC companies compute the critical path in dedicated scheduling software,
not by hand, and just embed its output.

This app doesn't attempt to reimplement a general CPM engine (forward/
backward pass, float calculation) -- ScheduleTask instead stores the
schedule AS ALREADY COMPUTED by Microsoft Project (Start/Finish/
TotalSlack/Critical are all read directly from the .mpp file via COM
automation; see reports.management.commands.import_ms_project_schedule),
the same way the reference template's own author would paste a Primavera
screenshot. Note the BOQ phase breakdown (progress_models.ProjectPhase)
uses a different work-breakdown structure than the .mpp schedule (BOQ is
organized by trade/scope across the whole building; the schedule is
organized floor-by-floor) -- the two are NOT reconciled row-by-row, this
model is a separate, independent source of truth for schedule/critical-
path reporting only.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from projects.models import Project


class ScheduleTask(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='schedule_tasks',
        help_text=_('Project this schedule task belongs to')
    )

    source_task_id = models.PositiveIntegerField(
        help_text=_("The task's ID (row position) in the source .mpp file")
    )
    unique_id = models.PositiveIntegerField(
        help_text=_("The task's UniqueID in the source .mpp file (stable across reordering)")
    )

    name = models.CharField(max_length=500)
    outline_level = models.PositiveSmallIntegerField(default=1, help_text=_('WBS indentation level'))
    is_summary = models.BooleanField(default=False, help_text=_('True for a summary/parent task (rolled up from children)'))
    is_milestone = models.BooleanField(default=False)

    start_date = models.DateField(null=True, blank=True)
    finish_date = models.DateField(null=True, blank=True)
    duration_days = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text=_('Working-day duration, as computed by the scheduling software')
    )
    duration_text = models.CharField(max_length=50, blank=True, help_text=_('e.g. "34 days" -- as displayed by the source software'))
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    total_slack_days = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text=_('Total float, in working days, as computed by the scheduling software')
    )
    is_critical = models.BooleanField(
        default=False,
        help_text=_("True if the scheduling software flagged this task as being on the project's critical path")
    )

    # Primavera-style extras for the schedule (Gantt) page. All optional: an imported MS Project schedule leaves them empty.
    activity_id = models.CharField(max_length=30, blank=True, help_text=_('Activity ID as shown in the schedule, e.g. A1010'))
    baseline_start = models.DateField(null=True, blank=True, help_text=_('Start in the approved baseline schedule'))
    baseline_finish = models.DateField(null=True, blank=True, help_text=_('Finish in the approved baseline schedule'))
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)

    predecessors = models.CharField(max_length=255, blank=True, help_text=_('Raw predecessor list, as shown by the source software (e.g. "10,15FS+14 days")'))
    resource_names = models.CharField(max_length=255, blank=True)

    source_file_name = models.CharField(max_length=255, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Schedule Task')
        verbose_name_plural = _('Schedule Tasks')
        ordering = ['project', 'source_task_id']
        unique_together = ('project', 'source_task_id')
        indexes = [
            models.Index(fields=['project', 'is_critical']),
        ]

    def __str__(self):
        return f"{self.project.project_symbol} - #{self.source_task_id} {self.name}"


class PhaseScheduleLink(models.Model):
    """
    Links a BOQ phase (the contract breakdown the owner is paid by) to the MS Project plan tasks that carry its work, so the plan
    can be compared with the actual progress per phase (reports.services.plan_vs_actual). It stores the task's MS Project Unique
    ID rather than the ScheduleTask row, so the links survive re-importing the schedule (which recreates every task row).
    A phase without any link is simply not part of the comparison; the owner's report keeps using the contract breakdown.
    """
    phase = models.ForeignKey('reports.ProjectPhase', on_delete=models.CASCADE, related_name='schedule_links')
    task_unique_id = models.PositiveIntegerField(help_text=_("MS Project Unique ID of a (leaf) plan task that carries this phase's work"))

    class Meta:
        unique_together = ('phase', 'task_unique_id')
        ordering = ['phase', 'task_unique_id']
        verbose_name = _('Phase / plan task link')
        verbose_name_plural = _('Phase / plan task links')

    def __str__(self):
        return f"{self.phase} -> plan task {self.task_unique_id}"
