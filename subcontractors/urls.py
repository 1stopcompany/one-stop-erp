from django.urls import path
from . import views

app_name = 'subcontractors'

urlpatterns = [
    path('', views.subcontractors_dashboard, name='dashboard'),
    path('general-terms/', views.general_terms, name='general_terms'),
    path('agreements/', views.agreement_list, name='agreement_list'),
    path('agreements/project/<int:project_pk>/create/', views.agreement_create, name='agreement_create'),
    path('agreements/<int:pk>/', views.agreement_detail, name='agreement_detail'),
    path('agreements/<int:pk>/edit/', views.agreement_edit, name='agreement_edit'),
    path('agreements/<int:pk>/pdf/', views.agreement_pdf, name='agreement_pdf'),
    path('agreements/<int:pk>/status/<str:new_status>/', views.agreement_status_update, name='agreement_status_update'),
    path('agreements/<int:pk>/lines/add/', views.agreement_line_add, name='agreement_line_add'),
    path('agreements/<int:pk>/lines/<int:line_pk>/delete/', views.agreement_line_delete, name='agreement_line_delete'),
    path('agreements/<int:pk>/payments/add/', views.agreement_payment_add, name='agreement_payment_add'),
    path('agreements/<int:pk>/payments/<int:payment_pk>/delete/', views.agreement_payment_delete, name='agreement_payment_delete'),
]
