from django.urls import path
from . import views

app_name = 'blueprints'

urlpatterns = [
    path('', views.blueprints_dashboard, name='dashboard'),
    path('manual.pdf', views.manual_pdf, name='manual_pdf'),
    path('project/<int:project_pk>/', views.project_drawings, name='project_drawings'),
    path('project/<int:project_pk>/add/', views.blueprint_add, name='blueprint_add'),
    path('drawing/<int:blueprint_pk>/revision/add/', views.revision_add, name='revision_add'),
    path('revision/<int:revision_pk>/review/', views.revision_review, name='revision_review'),
]
