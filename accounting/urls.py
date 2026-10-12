from django.urls import path
from . import views

app_name = 'accounting'

urlpatterns = [
    path('', views.accounting_dashboard, name='dashboard'),
    path('payables/', views.payables, name='payables'),
    path('payables/<int:pk>/pay/', views.payable_pay, name='payable_pay'),
    path('payables/<int:pk>/reopen/', views.payable_reopen, name='payable_reopen'),
]
