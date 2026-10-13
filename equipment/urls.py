from django.urls import path
from . import api_mobile, views, views_claims

app_name = 'equipment'

urlpatterns = [
    # the phone's equipment screens (api_mobile.py)
    path('api/mobile/tools/', api_mobile.mobile_tools, name='mobile_tools'),
    path('api/mobile/tools/by-code/<str:code>/', api_mobile.mobile_tool_by_code, name='mobile_tool_by_code'),
    path('api/mobile/tools/<int:pk>/', api_mobile.mobile_tool_detail, name='mobile_tool_detail'),
    path('api/mobile/tools/<int:pk>/request/', api_mobile.mobile_tool_request, name='mobile_tool_request'),
    path('api/mobile/destinations/', api_mobile.mobile_destinations, name='mobile_destinations'),
    path('api/mobile/transfers/', api_mobile.mobile_transfers, name='mobile_transfers'),
    path('api/mobile/transfers/<int:pk>/<str:action>/', api_mobile.mobile_transfer_action, name='mobile_transfer_action'),
    path('', views.equipment_dashboard, name='dashboard'),
    path('tools/', views.tool_list, name='tool_list'),
    path('tools/add/', views.tool_add, name='tool_add'),
    path('tools/labels/', views.labels_pdf, name='labels_pdf'),
    path('tools/catalog/', views.catalog_pdf, name='catalog_pdf'),
    path('tools/<int:pk>/', views.tool_detail, name='tool_detail'),
    path('tools/<int:pk>/edit/', views.tool_edit, name='tool_edit'),
    path('tools/<int:pk>/sheet/', views.tool_sheet_pdf, name='tool_sheet_pdf'),
    path('tools/<int:pk>/photo/', views.tool_photo, name='tool_photo'),
    path('tools/<int:pk>/request/', views.transfer_request, name='transfer_request'),
    path('tools/<int:pk>/maintenance/', views.maintenance_open, name='maintenance_open'),
    path('code/<str:code>/', views.tool_by_code, name='tool_by_code'),
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/<int:pk>/<str:action>/', views.transfer_action, name='transfer_action'),
    path('maintenance/<int:pk>/update/', views.maintenance_update, name='maintenance_update'),
    path('claims/', views_claims.claim_list, name='claim_list'),
    path('claims/<int:pk>/', views_claims.claim_detail, name='claim_detail'),
    path('claims/<int:pk>/review/', views_claims.claim_review, name='claim_review'),
]
