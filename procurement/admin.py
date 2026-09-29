from django.contrib import admin

from .models import (
    ItemMaster, Vendor,
    PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, RFQVendor, VendorQuote, VendorQuoteLine,
    PurchaseOrder, PurchaseOrderLine, POReceipt,
    ItemFamily, ItemGroup, ItemClassification, ItemBrand,
)


@admin.register(ItemMaster)
class ItemMasterAdmin(admin.ModelAdmin):
    list_display = ("full_code", "description", "brand", "unit", "status")
    list_filter = ("status", "aa_level")
    search_fields = ("full_code", "short_code", "source_code", "description", "brand")


@admin.register(ItemFamily)
class ItemFamilyAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(ItemGroup)
class ItemGroupAdmin(admin.ModelAdmin):
    list_display = ("family", "code", "name")
    list_filter = ("family",)
    search_fields = ("code", "name")


@admin.register(ItemClassification)
class ItemClassificationAdmin(admin.ModelAdmin):
    list_display = ("group", "code", "name")
    list_filter = ("group__family",)
    search_fields = ("code", "name")


@admin.register(ItemBrand)
class ItemBrandAdmin(admin.ModelAdmin):
    list_display = ("classification", "code", "name")
    list_filter = ("classification__group__family",)
    search_fields = ("code", "name")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "email", "rating", "is_active")
    search_fields = ("name", "contact_person", "email")
    list_filter = ("is_active",)


class PurchaseRequisitionLineInline(admin.TabularInline):
    model = PurchaseRequisitionLine
    extra = 1


@admin.register(PurchaseRequisition)
class PurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ("pr_number", "project", "status", "requested_by", "approved_by", "assigned_to", "required_date")
    list_filter = ("status", "project")
    search_fields = ("pr_number",)
    inlines = [PurchaseRequisitionLineInline]


class RFQVendorInline(admin.TabularInline):
    model = RFQVendor
    extra = 1


@admin.register(RequestForQuotation)
class RequestForQuotationAdmin(admin.ModelAdmin):
    list_display = ("rfq_number", "pr", "status", "due_date", "created_by")
    list_filter = ("status",)
    search_fields = ("rfq_number",)
    inlines = [RFQVendorInline]


class VendorQuoteLineInline(admin.TabularInline):
    model = VendorQuoteLine
    extra = 1
    fields = ("pr_line", "unit_price", "lead_time_days", "is_selected", "remarks")


@admin.register(VendorQuote)
class VendorQuoteAdmin(admin.ModelAdmin):
    list_display = ("rfq", "vendor", "received_date")
    inlines = [VendorQuoteLineInline]


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("po_number", "project", "vendor", "status", "total_price", "delivery_date")
    list_filter = ("status", "project")
    search_fields = ("po_number",)
    inlines = [PurchaseOrderLineInline]


@admin.register(POReceipt)
class POReceiptAdmin(admin.ModelAdmin):
    list_display = ("po_line", "quantity_received", "received_date", "received_by")
    search_fields = ("po_line__po__po_number",)


from .models import Warehouse, StockLevel, StockMovement  # noqa: E402


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "project", "is_active")
    list_filter = ("is_active",)


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "item", "quantity", "min_quantity", "reorder_quantity")
    list_filter = ("warehouse",)
    search_fields = ("item__full_code", "item__description")
    readonly_fields = ("quantity",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_date", "warehouse", "item", "movement_type", "quantity", "balance_after", "project")
    list_filter = ("warehouse", "movement_type")
    search_fields = ("item__full_code", "item__description")
    readonly_fields = [f.name for f in StockMovement._meta.fields]
