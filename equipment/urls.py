from django.urls import path
from . import views

app_name = 'equipment'

urlpatterns = [
    path('', views.equipment_dashboard, name='dashboard'),
    path('tools/', views.tool_list, name='tool_list'),
    path('tools/add/', views.tool_add, name='tool_add'),
    path('tools/labels/', views.labels_pdf, name='labels_pdf'),
    path('tools/<int:pk>/', views.tool_detail, name='tool_detail'),
    path('tools/<int:pk>/edit/', views.tool_edit, name='tool_edit'),
    path('tools/<int:pk>/request/', views.transfer_request, name='transfer_request'),
    path('tools/<int:pk>/maintenance/', views.maintenance_open, name='maintenance_open'),
    path('code/<str:code>/', views.tool_by_code, name='tool_by_code'),
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/<int:pk>/<str:action>/', views.transfer_action, name='transfer_action'),
    path('maintenance/<int:pk>/update/', views.maintenance_update, name='maintenance_update'),
]
