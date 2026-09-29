from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('specifications/', views.specifications_list, name='specifications_list'),
    path('specifications/add/', views.specification_volume_add, name='specification_volume_add'),
    path('specifications/<int:pk>/delete/', views.specification_volume_delete, name='specification_volume_delete'),
    path('specifications/<int:volume_pk>/sections/add/', views.specification_section_add, name='specification_section_add'),
    path('specifications/sections/<int:pk>/', views.specification_section_detail, name='specification_section_detail'),
    path('specifications/sections/<int:pk>/edit/', views.specification_section_edit, name='specification_section_edit'),
    path('specifications/sections/<int:pk>/pdf/', views.specification_section_pdf, name='specification_section_pdf'),
]
