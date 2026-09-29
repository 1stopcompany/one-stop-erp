from django.urls import path
from . import views, views_workflow, views_specifications

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='project_list'),
    path('create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/edit/', views.ProjectUpdateView.as_view(), name='project_edit'),
    path('<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('<int:project_pk>/floors/', views.ProjectFloorListView.as_view(), name='project_floors'),
    path('<int:project_pk>/floors/create/', views.ProjectFloorCreateView.as_view(), name='floor_create'),
    path('<int:pk>/reports/', views.ProjectReportsView.as_view(), name='project_reports'),
    path('<int:pk>/workflow/', views_workflow.workflow_view, name='workflow'),
    path('<int:pk>/workflow/insurance/add/', views_workflow.insurance_add, name='insurance_add'),
    path('<int:pk>/workflow/insurance/<int:doc_pk>/delete/', views_workflow.insurance_delete, name='insurance_delete'),
    path('<int:pk>/workflow/tender/add/', views_workflow.tender_add, name='tender_add'),
    path('<int:pk>/workflow/tender/<int:doc_pk>/delete/', views_workflow.tender_delete, name='tender_delete'),
    path('<int:pk>/workflow/regulatory/add/', views_workflow.regulatory_add, name='regulatory_add'),
    path('<int:pk>/workflow/regulatory/<int:doc_pk>/delete/', views_workflow.regulatory_delete, name='regulatory_delete'),
    path('<int:pk>/workflow/plans/add/', views_workflow.plan_add, name='plan_add'),
    path('<int:pk>/workflow/plans/<int:doc_pk>/delete/', views_workflow.plan_delete, name='plan_delete'),
    path('<int:pk>/workflow/plans/<int:plan_pk>/checklist/', views_workflow.plan_checklist_update, name='plan_checklist_update'),
    path('<int:pk>/workflow/<str:key>/complete/', views_workflow.stage_complete, name='stage_complete'),
    path('<int:pk>/specifications/', views_specifications.project_specifications, name='project_specifications'),
    path('<int:pk>/specifications/<int:section_pk>/toggle/', views_specifications.project_specification_toggle, name='project_specification_toggle'),
    path('api/budget-vs-actual/', views.BudgetVsActualAPI.as_view(), name='api_budget_vs_actual'),
   
]
