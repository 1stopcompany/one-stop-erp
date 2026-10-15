from django.urls import path
from . import views, views_claims

app_name = 'accounting'

urlpatterns = [
    path('', views.accounting_dashboard, name='dashboard'),
    path('payables/', views.payables, name='payables'),
    path('payables/<int:pk>/pay/', views.payable_pay, name='payable_pay'),
    path('payables/<int:pk>/reopen/', views.payable_reopen, name='payable_reopen'),
    path('payables/<int:pk>/claim/', views_claims.claim_from_equipment, name='claim_from_equipment'),
    # payment claims (the claim form)
    path('claims/', views_claims.claim_list, name='claim_list'),
    path('claims/new/', views_claims.claim_new, name='claim_new'),
    path('claims/report/', views_claims.claims_report, name='claims_report'),
    path('claims/<int:pk>/', views_claims.claim_detail, name='claim_detail'),
    path('claims/<int:pk>/edit/', views_claims.claim_edit, name='claim_edit'),
    path('claims/<int:pk>/pdf/', views_claims.claim_pdf, name='claim_pdf'),
    path('claims/<int:pk>/<str:action>/', views_claims.claim_action, name='claim_action'),
]
