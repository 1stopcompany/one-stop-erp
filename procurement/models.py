from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


def d2(x) -> Decimal:
    if x is None:
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"))


UNIT_CHOICES = [
    ("m", "Meter"),
    ("m2", "Square Meter"),
    ("m3", "Cubic Meter"),
    ("pcs", "Pieces"),
    ("set", "Set"),
    ("lot", "Lot"),
    ("kg", "Kilogram"),
    ("ton", "Ton"),
    ("bag", "Bag"),
    ("box", "Box"),
    ("roll", "Roll"),
    ("sheet", "Sheet"),
    ("liter", "Liter"),
]


class ItemFamily(models.Model):
    """
    Level 1 of the item classification hierarchy (ItemMaster.aa_level) --
    "Family" in the source workbook ("FINAL_With_Validation-R02.xlsx",
    sheet "FAMILY"): 18 fixed divisions (General Requirements, Concrete,
    Masonry, ...). Lets the Add/Edit Item form offer a real "pick by
    name" cascading list instead of asking someone to already know the
    2-digit code, per the client's request -- see
    procurement.management.commands.import_item_classification_tree.
    """
    code = models.CharField(max_length=2, primary_key=True, help_text="aa_level, e.g. '03'")
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "Item families"

    def __str__(self):
        return f"{self.code} - {self.name}"


class ItemGroup(models.Model):
    """Level 2 (ItemMaster.bb_category) -- "Group" in the source workbook, unique within its family."""
    family = models.ForeignKey(ItemFamily, on_delete=models.PROTECT, related_name="groups")
    code = models.CharField(max_length=2, help_text="bb_category, e.g. '04'")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = [("family", "code")]
        ordering = ["family__code", "code"]

    def __str__(self):
        return f"{self.family.code}.{self.code} - {self.name}"


class ItemClassification(models.Model):
    """Level 3 (ItemMaster.cc_subcategory) -- "Classification" in the source workbook, unique within its group."""
    group = models.ForeignKey(ItemGroup, on_delete=models.PROTECT, related_name="classifications")
    code = models.CharField(max_length=2, help_text="cc_subcategory, e.g. '01'")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = [("group", "code")]
        ordering = ["group__family__code", "group__code", "code"]

    def __str__(self):
        return f"{self.group.family.code}.{self.group.code}.{self.code} - {self.name}"


class ItemBrand(models.Model):
    """
    Level 4 (ItemMaster.dd_itemtype) -- "Brand" in the source workbook,
    the 4th step of its own Family -> Group -> Classification -> Brand ->
    item hierarchy. Despite the name, its real values are subcategory-like
    names (e.g. "Nails", "Cutting Discs", "General"), not manufacturer
    brands -- ItemMaster's own free-text `brand` field is the actual
    manufacturer brand, a separate and unrelated thing. Unique within its
    classification.
    """
    classification = models.ForeignKey(ItemClassification, on_delete=models.PROTECT, related_name="brands")
    code = models.CharField(max_length=2, help_text="dd_itemtype, e.g. '01'")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = [("classification", "code")]
        ordering = ["classification__group__family__code", "classification__group__code", "classification__code", "code"]

    def __str__(self):
        return f"{self.classification} / {self.code} - {self.name}"


class ItemMaster(models.Model):
    """
    The company's coded item classification (One Stop's own procurement
    coding scheme -- see reports.progress_models docstrings for a similar
    real-world-first design philosophy). full_code is the DB-unique
    "OS.AA.BB.CC.DD.EEE" identifier this app already used before this
    item catalog was imported; source_code is the plain 11-digit code as
    it appears in the company's own item classification spreadsheet
    ("FINAL_With_Validation-R02.xlsx", sheet "ALL"), kept for traceability
    since it is NOT guaranteed unique in the source file (~18 codes there
    cover more than one distinct item -- see
    procurement.management.commands.import_item_master). variant_suffix
    disambiguates those cases without inventing a fake spec code.

    Unlike the source spreadsheet, `unit` is NOT required here: the real
    unit of measure isn't tracked per catalog entry, only per purchase-
    requisition line (the same generic item can reasonably be requested
    in different units depending on context) -- see
    PurchaseRequisitionLine.unit.
    """

    organization = models.CharField(max_length=2, default="OS", editable=False)

    aa_level = models.CharField(max_length=2, help_text="Specs TOC Section (01-18)")
    bb_category = models.CharField(max_length=2, help_text="Category code")
    cc_subcategory = models.CharField(max_length=2, help_text="Sub-category code")
    dd_itemtype = models.CharField(max_length=2, help_text="Item type code")
    eee_attribute = models.CharField(max_length=3, default="000", help_text="DN size/thickness/grade or 000")
    variant_suffix = models.PositiveSmallIntegerField(
        default=0,
        help_text="Disambiguates source rows that legitimately share one classification code but are different items (0 = no conflict)",
    )

    full_code = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    short_code = models.CharField(max_length=20, db_index=True, editable=False)
    source_code = models.CharField(
        max_length=20, blank=True, db_index=True,
        help_text="Original 11-digit code from the source item-classification spreadsheet, if imported from it",
    )
    barcode_value = models.CharField(
        max_length=20, unique=True, editable=False, blank=True, default="",
        help_text=(
            "Scannable Code128 value: the item's own Family/Group/Classification/Brand/attribute "
            "codes, each letter-prefixed so the barcode's own text is self-describing on sight "
            "(e.g. 'F03G04C01B01T000'), plus a variant suffix if the item has one -- confirmed "
            "with the client as preferable to a plain numeric code with a check digit."
        ),
    )

    description = models.CharField(max_length=500)
    brand = models.CharField(max_length=200, blank=True, help_text="Brand/manufacturer, if known")
    unit = models.CharField(
        max_length=20, choices=UNIT_CHOICES, blank=True,
        help_text="Typical unit of measure, for reference only -- the actual unit is chosen per purchase-requisition line",
    )
    standard = models.CharField(max_length=100, blank=True)
    batch_reference = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("inactive", "Inactive")],
        default="active",
    )

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["full_code"]
        indexes = [
            models.Index(fields=["full_code"]),
            models.Index(fields=["short_code"]),
            models.Index(fields=["aa_level"]),
            models.Index(fields=["source_code"]),
        ]

    def save(self, *args, **kwargs):
        # Normalize pieces
        aa = (self.aa_level or "").strip().zfill(2)
        bb = (self.bb_category or "").strip().zfill(2)
        cc = (self.cc_subcategory or "").strip().zfill(2)
        dd = (self.dd_itemtype or "").strip().zfill(2)
        eee = (self.eee_attribute or "000").strip().zfill(3)

        self.aa_level, self.bb_category, self.cc_subcategory, self.dd_itemtype, self.eee_attribute = aa, bb, cc, dd, eee
        base_code = f"{self.organization}.{aa}.{bb}.{cc}.{dd}.{eee}"
        self.full_code = f"{base_code}.{self.variant_suffix}" if self.variant_suffix else base_code
        self.short_code = f"{aa}.{bb}.{cc}.{dd}"

        self.barcode_value = f"F{aa}G{bb}C{cc}B{dd}T{eee}"
        if self.variant_suffix:
            self.barcode_value += f"V{self.variant_suffix}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_code} - {self.description}"


class Vendor(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)

    rating = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseRequisition(models.Model):
    """
    A site's request for materials/supplies (matches the real "طلب لوازم
    من المستودع" / PER-01 form in the company's ISO 9001:2015 procurement
    procedure, QMS-PRO-06 / QP-30): one request can list several items at
    once (see PurchaseRequisitionLine), submitted by a site engineer for
    a specific project and approved or rejected by that project's
    manager. This app doesn't yet implement the warehouse-stock-check
    step (أمين المستودع) from the ISO procedure -- every submitted
    request goes straight to the project manager for approval, then (once
    approved) to procurement; that step can be layered in later without
    changing this model.
    """

    STATUS = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("in_procurement", "In Procurement"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    pr_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="purchase_requisitions")

    required_date = models.DateField(help_text="Date the materials are needed by")
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    remarks = models.TextField(blank=True)
    rejected_reason = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="prs_requested", help_text="Site engineer who created this request",
    )
    approved_by = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="prs_approved", help_text="Project manager who approved/rejected this request",
    )
    approved_date = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="prs_assigned", help_text="Procurement officer tracking this request",
    )

    submitted_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["pr_number"]),
            models.Index(fields=["project", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.pr_number:
            ts = timezone.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            self.pr_number = f"PR-{self.project_id}-{ts}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.pr_number


class PurchaseRequisitionLine(models.Model):
    pr = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name="pr_lines")
    sub_item = models.ForeignKey(
        "reports.ProjectPhaseSubItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="pr_lines",
        help_text="The project BOQ item this material is bought for -- what cost control charges it to",
    )

    quantity_requested = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    remarks = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["pr", "order", "id"]

    def __str__(self):
        return f"{self.pr.pr_number} - {self.item.full_code} x{self.quantity_requested}{self.unit}"


class RequestForQuotation(models.Model):
    """
    An RFQ issued by the Procurement Officer against an approved PR (see
    QP-30's "الشراء من خلال تجهيز عروض أسعار RFQ" section: PER-03). This
    app doesn't send the RFQ itself (real practice is fax/email/WhatsApp
    per the ISO procedure) -- it tracks which vendors were invited and
    records each vendor's quote once received, for side-by-side
    comparison and PO generation.
    """

    STATUS = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    rfq_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    pr = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name="rfqs")

    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="rfqs_created")
    sent_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_date"]

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            ts = timezone.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            self.rfq_number = f"RFQ-{self.pr_id}-{ts}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.rfq_number


class RFQVendor(models.Model):
    """One vendor invited to quote on an RFQ."""
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name="invited_vendors")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="rfq_invitations")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("rfq", "vendor")]

    def __str__(self):
        return f"{self.rfq.rfq_number} -> {self.vendor.name}"


class VendorQuote(models.Model):
    """One vendor's price quote in response to an RFQ, with one line per PR line quoted."""
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name="quotes")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="quotes")

    received_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    entered_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotes_entered")
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("rfq", "vendor")]
        ordering = ["-created_date"]

    def total_price(self):
        return sum((line.total_price for line in self.lines.all()), Decimal("0.00"))

    def __str__(self):
        return f"{self.rfq.rfq_number} - {self.vendor.name}"


class VendorQuoteLine(models.Model):
    """
    One vendor's quoted price for one PR line. Selection is done at THIS
    level (is_selected), not on the whole VendorQuote -- a real RFQ often
    ends up sourced from more than one vendor (e.g. cement from the
    cheapest quote, steel from another), so "pick one winning quote for
    everything" doesn't match how procurement actually awards RFQs. At
    most one VendorQuoteLine across all quotes for a given pr_line should
    be selected at a time -- see views.rfq_select_lines, which enforces
    that when saving a selection.
    """
    quote = models.ForeignKey(VendorQuote, on_delete=models.CASCADE, related_name="lines")
    pr_line = models.ForeignKey(PurchaseRequisitionLine, on_delete=models.CASCADE, related_name="quote_lines")

    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    is_selected = models.BooleanField(default=False, help_text="This vendor's price was chosen for this specific item")

    class Meta:
        unique_together = [("quote", "pr_line")]

    def save(self, *args, **kwargs):
        self.total_price = d2(d2(self.unit_price) * d2(self.pr_line.quantity_requested))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quote} - {self.pr_line.item.full_code}"


class PurchaseOrder(models.Model):
    STATUS = [
        ("draft", "Draft"),
        ("sent", "Sent to Vendor"),
        ("confirmed", "Confirmed"),
        ("partial_received", "Partially Received"),
        ("received", "Fully Received"),
        ("cancelled", "Cancelled"),
    ]

    po_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="purchase_orders")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="purchase_orders")

    pr = models.ForeignKey(PurchaseRequisition, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders")
    source_quote = models.ForeignKey(
        VendorQuote, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders",
        help_text="The winning RFQ quote this PO was generated from, if any (blank for a direct/emergency purchase)",
    )

    total_price = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    po_date = models.DateTimeField(auto_now_add=True)
    delivery_date = models.DateField()
    actual_delivery_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    remarks = models.TextField(blank=True)

    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="pos_created")
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-po_date"]
        indexes = [
            models.Index(fields=["po_number"]),
            models.Index(fields=["vendor", "status"]),
            models.Index(fields=["project", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.po_number:
            ts = timezone.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            base = f"PO-{self.vendor_id}-{ts}"
            # Millisecond stamps can collide when several orders are created back to back (a seeding
            # script, a bulk import) -- add a counter rather than fail on the unique constraint.
            number, n = base, 1
            while PurchaseOrder.objects.filter(po_number=number).exists():
                n += 1
                number = f"{base}-{n}"
            self.po_number = number
        super().save(*args, **kwargs)

    def recalculate_total(self):
        total = self.lines.aggregate(s=models.Sum("total_price"))["s"] or Decimal("0.00")
        PurchaseOrder.objects.filter(pk=self.pk).update(total_price=d2(total))

    def refresh_status_from_lines(self):
        if self.status == "cancelled":
            return
        lines = list(self.lines.all())
        if not lines:
            return
        q_ord = sum((l.quantity_ordered for l in lines), Decimal("0"))
        q_rec = sum((l.quantity_received for l in lines), Decimal("0"))
        if q_rec <= 0:
            new_status = self.status if self.status in ("draft", "sent", "confirmed") else "confirmed"
        elif q_rec < q_ord:
            new_status = "partial_received"
        else:
            new_status = "received"
        if new_status != self.status:
            PurchaseOrder.objects.filter(pk=self.pk).update(status=new_status)
            self.status = new_status

    def __str__(self):
        return self.po_number


class PurchaseOrderLine(models.Model):
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name="po_lines")
    pr_line = models.ForeignKey(PurchaseRequisitionLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="po_lines")
    sub_item = models.ForeignKey(
        "reports.ProjectPhaseSubItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="po_lines",
        help_text="The project BOQ item this purchase is charged to (copied from the requisition line when there is one)",
    )

    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    class Meta:
        ordering = ["po", "id"]

    def save(self, *args, **kwargs):
        self.total_price = d2(d2(self.quantity_ordered) * d2(self.unit_price))
        super().save(*args, **kwargs)
        self.po.recalculate_total()

    def __str__(self):
        return f"{self.po.po_number} - {self.item.full_code}"


class POReceipt(models.Model):
    """One receipt transaction against a specific PO line."""
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.CASCADE, related_name="receipts")

    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    received_date = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="po_receipts")
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_date"]
        indexes = [
            models.Index(fields=["po_line", "received_date"]),
        ]

    def __str__(self):
        return f"{self.po_line} - {self.quantity_received}"


# ==================== Warehouse / stock ====================

class Warehouse(models.Model):
    """
    A physical store (main yard/warehouse or a site store). Stock is tracked per
    warehouse + item (see StockLevel). `project` optionally marks a site store as
    belonging to one project, so goods received against that project's POs land
    in it automatically (see services_warehouse.warehouse_for_receipt).
    """
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="warehouses",
        help_text="Leave blank for a general/main warehouse; set it for a project's own site store",
    )
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockLevel(models.Model):
    """
    Current on-hand quantity of one item in one warehouse, plus the limits that
    drive re-ordering. `quantity` is never edited directly -- it is only changed
    by services_warehouse.record_movement(), which also writes the StockMovement
    ledger row, so the two can't drift apart.
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="stock_levels")
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name="stock_levels")

    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    min_quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="Minimum stock. The quantity on hand must not drop below this -- once it reaches it, the item must be re-ordered (0 = no limit)",
    )
    reorder_quantity = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="How much to order when the item runs low (0 = order enough to get back to twice the minimum)",
    )
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("warehouse", "item")]
        ordering = ["item__full_code", "warehouse__name"]

    @property
    def is_low(self):
        """At or below the limit (and a limit is actually set)."""
        return self.min_quantity > 0 and self.quantity <= self.min_quantity

    @property
    def status(self):
        if self.min_quantity > 0 and self.quantity <= 0:
            return "out"
        if self.is_low:
            return "low"
        return "ok"

    @property
    def suggested_order_quantity(self):
        if not self.is_low:
            return Decimal("0.00")
        if self.reorder_quantity > 0:
            return self.reorder_quantity
        return max(self.min_quantity * 2 - self.quantity, Decimal("0.00"))

    def __str__(self):
        return f"{self.warehouse} - {self.item.full_code}: {self.quantity}"


class StockMovement(models.Model):
    """Append-only ledger: every change to a StockLevel.quantity has exactly one row here."""
    TYPES = [
        ("receipt", "Received from supplier"),
        ("issue", "Issued to project"),
        ("adjustment", "Stock count / correction"),
    ]

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=TYPES)
    quantity = models.DecimalField(max_digits=14, decimal_places=2, help_text="Signed: positive = in, negative = out")
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    project = models.ForeignKey("projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    po_receipt = models.ForeignKey(POReceipt, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    remarks = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date", "-id"]
        indexes = [models.Index(fields=["warehouse", "item", "created_date"])]

    def __str__(self):
        return f"{self.warehouse} {self.item.full_code} {self.quantity:+}"
