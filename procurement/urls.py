from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, views_warehouse

app_name = "procurement"

router = DefaultRouter()
router.register(r"items", views.ItemViewSet, basename="api_items")
router.register(r"vendors", views.VendorViewSet, basename="api_vendors")
router.register(r"prs", views.PRViewSet, basename="api_prs")
router.register(r"pos", views.POViewSet, basename="api_pos")
router.register(r"receipts", views.ReceiptViewSet, basename="api_receipts")

urlpatterns = [
    path("", views.ProcurementDashboardView.as_view(), name="dashboard"),
    path("manual.pdf", views.ProcurementManualPdfView.as_view(), name="manual_pdf"),

    path("items/", views.ItemListView.as_view(), name="item_list"),
    path("items/create/", views.ItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/", views.ItemDetailView.as_view(), name="item_detail"),
    path("items/<int:pk>/edit/", views.ItemUpdateView.as_view(), name="item_update"),
    path("items/<int:pk>/delete/", views.ItemDeleteView.as_view(), name="item_delete"),
    path("items/<int:pk>/barcode.png", views.ItemBarcodeImageView.as_view(), name="item_barcode_png"),
    path("items/<int:pk>/label.pdf", views.ItemLabelPdfView.as_view(), name="item_label_pdf"),
    path("items/scan/", views.item_scan_lookup, name="item_scan_lookup"),
    path("items/check-code/", views.item_code_check, name="item_code_check"),
    # Alias names for old templates
    path("items/create/", views.ItemCreateView.as_view(), name="item_master_create"),
    path("items/", views.ItemListView.as_view(), name="item_master_list"),
    path("items/<int:pk>/", views.ItemDetailView.as_view(), name="item_master_detail"),
    path("items/<int:pk>/edit/", views.ItemUpdateView.as_view(), name="item_master_update"),
    path("items/<int:pk>/delete/", views.ItemDeleteView.as_view(), name="item_master_delete"),


    # ---- Purchase Requisitions ----
    path("pr/", views.PRListView.as_view(), name="pr_list"),
    path("pr/create/", views.pr_create, name="pr_create"),
    path("pr/<int:pk>/", views.PRDetailView.as_view(), name="pr_detail"),
    path("pr/<int:pk>/edit/", views.pr_edit, name="pr_update"),
    path("pr/<int:pk>/submit/", views.PRSubmitView.as_view(), name="pr_submit"),
    path("pr/<int:pk>/approve/", views.PRApproveView.as_view(), name="pr_approve"),
    path("pr/<int:pk>/reject/", views.PRRejectView.as_view(), name="pr_reject"),
    path("pr/<int:pk>/claim/", views.PRClaimView.as_view(), name="pr_claim"),
    path("pr/<int:pk>/pdf/", views.PRPdfView.as_view(), name="pr_pdf"),
    path("pr/<int:pk>/delete/", views.PRDeleteView.as_view(), name="pr_delete"),

    # ---- RFQ ----
    path("rfq/", views.RFQListView.as_view(), name="rfq_list"),
    path("pr/<int:pr_id>/rfq/create/", views.rfq_create, name="rfq_create"),
    path("rfq/<int:pk>/", views.RFQDetailView.as_view(), name="rfq_detail"),
    path("rfq/<int:pk>/send/", views.RFQSendView.as_view(), name="rfq_send"),
    path("rfq/<int:pk>/quote/add/", views.rfq_add_quote, name="rfq_add_quote"),
    path("rfq/<int:pk>/select-lines/", views.rfq_select_lines, name="rfq_select_lines"),
    path("rfq/<int:pk>/create-po/", views.po_create_from_rfq, name="po_create_from_rfq"),

    # ---- Purchase Orders ----
    path("po/", views.POListView.as_view(), name="po_list"),
    path("po/create/", views.po_create, name="po_create"),
    path("po/<int:pk>/", views.PODetailView.as_view(), name="po_detail"),
    path("po/<int:pk>/send/", views.POSendView.as_view(), name="po_send"),
    path("po/<int:pk>/pdf/", views.POPdfView.as_view(), name="po_pdf"),
    path("po/<int:pk>/receive/", views.po_site_receive, name="po_site_receive"),
    path("po/<int:pk>/delete/", views.PODeleteView.as_view(), name="po_delete"),

    path("vendors/", views.VendorListView.as_view(), name="vendor_list"),
    path("vendors/create/", views.VendorCreateView.as_view(), name="vendor_create"),
    path("vendors/<int:pk>/", views.VendorDetailView.as_view(), name="vendor_detail"),
    path("vendors/<int:pk>/edit/", views.VendorUpdateView.as_view(), name="vendor_update"),
    path("vendors/<int:pk>/delete/", views.VendorDeleteView.as_view(), name="vendor_delete"),

    path("receipts/", views.POReceiptListView.as_view(), name="receipt_list"),
    path("receipts/create/", views.POReceiptCreateView.as_view(), name="receipt_create"),
    path("receipts/<int:pk>/", views.POReceiptDetailView.as_view(), name="receipt_detail"),
    path("receipts/<int:pk>/edit/", views.POReceiptUpdateView.as_view(), name="receipt_update"),

    # ---- Warehouse / stock ----
    path("warehouse/", views_warehouse.stock_list, name="stock_list"),
    path("warehouse/limit/", views_warehouse.stock_limit, name="stock_limit"),
    path("warehouse/issue/", views_warehouse.stock_issue, name="stock_issue"),
    path("warehouse/adjust/", views_warehouse.stock_adjust, name="stock_adjust"),
    path("warehouse/movements/", views_warehouse.stock_movements, name="stock_movements"),
    path("warehouse/reorder/", views_warehouse.reorder_list, name="stock_reorder"),
    path("warehouse/list/", views_warehouse.warehouse_list, name="warehouse_list"),
    path("warehouse/list/create/", views_warehouse.warehouse_form, name="warehouse_create"),
    path("warehouse/list/<int:pk>/edit/", views_warehouse.warehouse_form, name="warehouse_update"),

    path("api/", include(router.urls)),
]
