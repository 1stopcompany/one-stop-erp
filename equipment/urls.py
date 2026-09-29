from django.urls import path
from . import views

app_name = 'equipment'

urlpatterns = [
    path('', views.equipment_dashboard, name='dashboard'),
]
