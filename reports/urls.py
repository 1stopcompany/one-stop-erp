"""
Reports URL Configuration - Unified Daily and Monthly Reporting System

This module defines URL patterns for both daily and monthly reports.
"""

from django.urls import path
from . import views
from . import api_views, api_mobile
from . import views_print

app_name = 'reports'

urlpatterns = [
    # Report Type Selection
    path('', views.report_type_selection, name='report_type_selection'),
    path('select-project/<str:report_type>/', views.select_project_for_report, name='select_project'),
    path('approvals/', views.approvals_dashboard, name='approvals_dashboard'),
    
    # ==================== DAILY REPORT URLS ====================
    path('daily/', views.DailyReportListView.as_view(), name='daily_report_list'),
    path('daily/create/', views.DailyReportCreateView.as_view(), name='daily_report_create'),
    path('daily/<int:pk>/', views.DailyReportDetailView.as_view(), name='daily_report_detail'),
    path('daily/<int:pk>/edit/', views.DailyReportUpdateView.as_view(), name='daily_report_update'),
    path('daily/<int:pk>/submit/', views.submit_daily_report, name='submit_daily_report'),
    path('daily/<int:pk>/review/', views.review_daily_report, name='review_daily_report'),
    path('daily/<int:pk>/approve/', views.approve_daily_report, name='approve_daily_report'),
    path('daily/<int:pk>/export-pdf/', views.export_daily_pdf, name='export_daily_pdf'),
    path('daily/idle-days/create/', views.create_idle_day_reports_view, name='create_idle_day_reports'),
    path('deletions/', views.pending_deletions, name='pending_deletions'),
    path('<str:kind>/<int:pk>/delete/', views.delete_report, name='delete_report'),
    path('<str:kind>/<int:pk>/request-delete/', views.request_delete_report, name='request_delete_report'),
    path('<str:kind>/<int:pk>/restore/', views.restore_report, name='restore_report'),
    
    # ==================== DAILY REPORT API ENDPOINTS ====================
    # mobile app (token auth): the site engineer records the day-labor workers of a project's day
    path('api/mobile/projects/', api_mobile.my_projects, name='mobile_projects'),
    path('api/mobile/projects/<int:pk>/workers/', api_mobile.project_workers_day, name='mobile_workers_day'),
    path('api/mobile/workers/', api_mobile.search_workers, name='mobile_worker_search'),
    path('api/daily/section-order/', api_views.save_daily_report_section_order, name='api_save_daily_report_section_order'),
    path('api/daily/<int:report_id>/equipment/', api_views.add_daily_equipment, name='api_add_equipment'),
    path('api/daily/<int:report_id>/equipment/<int:equipment_id>/', api_views.delete_daily_equipment, name='api_delete_equipment'),
    path('api/daily/<int:report_id>/material/', api_views.add_daily_material, name='api_add_material'),
    path('api/daily/<int:report_id>/material/<int:material_id>/', api_views.delete_daily_material, name='api_delete_material'),
    path('api/daily/<int:report_id>/visitor/', api_views.add_daily_visitor, name='api_add_visitor'),
    path('api/daily/<int:report_id>/visitor/<int:visitor_id>/', api_views.delete_daily_visitor, name='api_delete_visitor'),
    path('api/daily/<int:report_id>/attachment/', api_views.add_daily_attachment, name='api_add_attachment'),
    path('api/daily/<int:report_id>/attachment/<int:attachment_id>/', api_views.delete_daily_attachment, name='api_delete_attachment'),
    path('api/daily/<int:report_id>/attachment/<int:attachment_id>/edit/', api_views.edit_daily_attachment, name='api_edit_attachment'),
    path('api/daily/<int:report_id>/remarks/', api_views.update_daily_report_remarks, name='api_update_daily_remarks'),
    path('api/daily/<int:report_id>/work-hours-note/', api_views.update_daily_report_work_hours_note, name='api_update_daily_work_hours_note'),

    # -- Worker attendance (named workers, Section 2) --
    path('api/daily-workers/', api_views.add_daily_worker, name='api_add_daily_worker'),
    path('api/equipment-master/', api_views.add_equipment_master, name='api_add_equipment_master'),
    path('api/labor-classifications/', api_views.add_labor_classification, name='api_add_labor_classification'),
    path('api/daily/<int:report_id>/crew/', api_views.add_daily_crew, name='api_add_daily_crew'),
    path('api/daily/<int:report_id>/crew/<int:crew_id>/edit/', api_views.edit_daily_crew, name='api_edit_daily_crew'),
    path('api/daily/<int:report_id>/crew/<int:crew_id>/', api_views.delete_daily_crew, name='api_delete_daily_crew'),
    path('api/daily/<int:report_id>/worker-attendance/', api_views.add_daily_worker_attendance, name='api_add_worker_attendance'),
    path('api/daily/<int:report_id>/worker-attendance/<int:entry_id>/', api_views.delete_daily_worker_attendance, name='api_delete_worker_attendance'),
    path('api/daily/<int:report_id>/worker-attendance/<int:entry_id>/edit/', api_views.edit_daily_worker_attendance, name='api_edit_worker_attendance'),
    path('api/daily/<int:report_id>/worker-attendance/<int:entry_id>/pull-gps/', api_views.pull_gps_daily_worker_attendance, name='api_pull_gps_worker_attendance'),

    # -- Activity progress (Section 1) --
    path('api/daily/<int:report_id>/activity-progress/', api_views.add_daily_activity_progress, name='api_add_activity_progress'),
    path('api/daily/<int:report_id>/activity-progress/<int:entry_id>/', api_views.delete_daily_activity_progress, name='api_delete_activity_progress'),

    # -- QA/QC & HSE (Section 4, one per report) --
    path('api/daily/<int:report_id>/qaqc/', api_views.save_daily_qaqc, name='api_save_qaqc'),

    # -- Next day plan (Section 6) --
    path('api/daily/<int:report_id>/next-day-plan/', api_views.add_daily_next_day_plan, name='api_add_next_day_plan'),
    path('api/daily/<int:report_id>/next-day-plan/<int:entry_id>/', api_views.delete_daily_next_day_plan, name='api_delete_next_day_plan'),

    # -- Site events: Delay/SI/RFI/NCR/HSE (Section 5) --
    path('api/daily/<int:report_id>/site-event/', api_views.add_daily_site_event, name='api_add_site_event'),
    path('api/daily/<int:report_id>/site-event/<int:event_id>/', api_views.delete_daily_site_event, name='api_delete_site_event'),
    
    # ==================== MONTHLY REPORT URLS ====================
    path('monthly/', views.MonthlyReportListView.as_view(), name='monthly_report_list'),
    path('monthly/create/', views.MonthlyReportCreateView.as_view(), name='monthly_report_create'),
    path('monthly/generate/', views.generate_monthly_report_view, name='monthly_report_generate'),
    path('monthly/<int:pk>/', views.MonthlyReportDetailView.as_view(), name='monthly_report_detail'),
    path('monthly/<int:pk>/dashboard/', views.MonthlyReportDashboardView.as_view(), name='monthly_report_dashboard'),
    path('monthly/<int:pk>/dashboard/export-pdf/', views.export_monthly_dashboard_pdf, name='export_monthly_dashboard_pdf'),
    path('monthly/<int:pk>/export-internal-pdf/', views.export_internal_monthly_pdf, name='export_internal_monthly_pdf'),
    path('monthly/<int:pk>/edit/', views.MonthlyReportUpdateView.as_view(), name='monthly_report_update'),
    path('monthly/<int:pk>/submit/', views.submit_monthly_report, name='submit_monthly_report'),
    path('monthly/<int:pk>/review/', views.review_monthly_report, name='review_monthly_report'),
    path('monthly/<int:pk>/approve/', views.approve_monthly_report, name='approve_monthly_report'),
    path('monthly/<int:pk>/export-pdf/', views.export_monthly_pdf, name='export_monthly_pdf'),

    # -------------------------
    # AJAX / JSON APIs (Monthly)
    # -------------------------
    path('api/monthly/<int:report_id>/floor-activities/', api_views.monthly_floor_activity_list_create, name='api_monthly_floor_activities'),
    path('api/monthly/<int:report_id>/floor-activities/<int:item_id>/', api_views.monthly_floor_activity_delete, name='api_monthly_floor_activities_delete'),

    path('api/monthly/<int:report_id>/external-works/', api_views.monthly_external_work_list_create, name='api_monthly_external_works'),
    path('api/monthly/<int:report_id>/external-works/<int:item_id>/', api_views.monthly_external_work_delete, name='api_monthly_external_works_delete'),

    path('api/monthly/<int:report_id>/materials/', api_views.monthly_material_supply_list_create, name='api_monthly_materials'),
    path('api/monthly/<int:report_id>/materials/<int:item_id>/', api_views.monthly_material_supply_update_delete, name='api_monthly_materials_update_delete'),
    path('api/monthly/<int:report_id>/materials/<int:item_id>/add-quantity/', api_views.monthly_material_supply_add_quantity, name='api_monthly_materials_add_quantity'),

    path('api/monthly/<int:report_id>/upcoming-works/', api_views.monthly_upcoming_work_list_create, name='api_monthly_upcoming_works'),
    path('api/monthly/<int:report_id>/upcoming-works/<int:item_id>/', api_views.monthly_upcoming_work_delete, name='api_monthly_upcoming_works_delete'),

    path('api/monthly/<int:report_id>/progress-items/', api_views.monthly_progress_category_item_list_create, name='api_monthly_progress_items'),
    path('api/monthly/<int:report_id>/progress-items/<int:item_id>/', api_views.monthly_progress_category_item_update_delete, name='api_monthly_progress_items_update_delete'),

    path('api/monthly/<int:report_id>/key-activities/', api_views.monthly_key_activity_list_create, name='api_monthly_key_activities'),
    path('api/monthly/<int:report_id>/key-activities/<int:item_id>/', api_views.monthly_key_activity_update_delete, name='api_monthly_key_activities_update_delete'),

    path('api/monthly/<int:report_id>/issues-risks-delays/', api_views.monthly_issue_risk_delay_list_create, name='api_monthly_issues_risks_delays'),
    path('api/monthly/<int:report_id>/issues-risks-delays/<int:item_id>/', api_views.monthly_issue_risk_delay_update_delete, name='api_monthly_issues_risks_delays_update_delete'),

    path('api/monthly/<int:report_id>/narrative/', api_views.monthly_report_update_narrative, name='api_monthly_report_update_narrative'),

    path('api/monthly/<int:report_id>/photos/', api_views.monthly_report_photo_list_create, name='api_monthly_report_photos'),
    path('api/monthly/<int:report_id>/photos/<int:photo_id>/', api_views.monthly_report_photo_update_delete, name='api_monthly_report_photos_update_delete'),

    path('api/monthly/<int:report_id>/attachment/', api_views.add_monthly_attachment, name='api_add_monthly_attachment'),
    path('api/monthly/<int:report_id>/attachment/<int:attachment_id>/', api_views.delete_monthly_attachment, name='api_delete_monthly_attachment'),
    path('api/monthly/<int:report_id>/attachment/<int:attachment_id>/edit/', api_views.edit_monthly_attachment, name='api_edit_monthly_attachment'),

    path('api/monthly/<int:report_id>/review-comments/', api_views.monthly_review_comment_list_create, name='api_monthly_review_comments'),
    path('api/monthly/<int:report_id>/review-comments/<int:item_id>/', api_views.monthly_review_comment_update_delete, name='api_monthly_review_comments_update_delete'),
    path('api/monthly/<int:report_id>/new-revision/', api_views.monthly_report_new_revision, name='api_monthly_report_new_revision'),
    path('api/monthly/<int:report_id>/reorder-section/', api_views.monthly_report_reorder_section, name='api_monthly_report_reorder_section'),

    # ==================== OWNER FINANCIAL REPORT URLS ====================
    path('owner-financial/', views.OwnerFinancialReportListView.as_view(), name='owner_financial_report_list'),
    path('owner-financial/create/', views.OwnerFinancialReportCreateView.as_view(), name='owner_financial_report_create'),
    path('owner-financial/<int:pk>/', views.OwnerFinancialReportDetailView.as_view(), name='owner_financial_report_detail'),
    path('owner-financial/<int:pk>/edit/', views.OwnerFinancialReportUpdateView.as_view(), name='owner_financial_report_update'),
    path('owner-financial/<int:pk>/copy/', views.copy_owner_financial_report, name='copy_owner_financial_report'),
    path('owner-financial/<int:pk>/submit/', views.submit_owner_financial_report, name='submit_owner_financial_report'),
    path('owner-financial/<int:pk>/review/', views.review_owner_financial_report, name='review_owner_financial_report'),
    path('owner-financial/<int:pk>/approve/', views.approve_owner_financial_report, name='approve_owner_financial_report'),
    path('owner-financial/<int:pk>/export-pdf/', views.export_owner_financial_pdf, name='export_owner_financial_pdf'),
    path('owner-financial/<int:pk>/freeze/', views.freeze_owner_report, name='freeze_owner_report'),

    path('api/owner-financial/<int:report_id>/price-items/', api_views.owner_report_price_item_list_create, name='api_owner_report_price_items'),
    path('api/owner-financial/<int:report_id>/price-items/<int:item_id>/', api_views.owner_report_price_item_delete, name='api_owner_report_price_items_delete'),
    path('api/owner-financial/<int:report_id>/price-items/<int:item_id>/add-quantity/', api_views.owner_report_price_item_add_quantity, name='api_owner_report_price_items_add_quantity'),

    path('api/owner-financial/<int:report_id>/phase-updates/', api_views.owner_report_phase_update_list_create, name='api_owner_report_phase_updates'),
    path('api/owner-financial/<int:report_id>/phase-updates/<int:item_id>/', api_views.owner_report_phase_update_update_delete, name='api_owner_report_phase_updates_update_delete'),
    path('api/owner-financial/<int:report_id>/phase-updates/<int:item_id>/move/', api_views.owner_report_phase_update_move, name='api_owner_report_phase_updates_move'),
    path('api/owner-financial/<int:report_id>/narrative/', api_views.owner_financial_report_update_narrative, name='api_owner_financial_report_update_narrative'),

    path('api/owner-financial/<int:report_id>/photos/', api_views.owner_report_photo_list_create, name='api_owner_report_photos'),
    path('api/owner-financial/<int:report_id>/photos/<int:photo_id>/', api_views.owner_report_photo_update_delete, name='api_owner_report_photos_update_delete'),

    # ==================== PROJECT PHASE PHOTO GALLERY ====================
    path('project/<int:project_id>/phase-photos/', views.phase_photo_gallery, name='phase_photo_gallery'),
    path('api/project/<int:project_id>/phase-photos/', api_views.add_phase_photo, name='api_add_phase_photo'),
    path('api/project/<int:project_id>/phase-photos/<int:photo_id>/', api_views.delete_phase_photo, name='api_delete_phase_photo'),

    # ==================== BOQ EDITOR ====================
    path('project/<int:project_id>/boq/', views.boq_editor, name='boq_editor'),
    path('project/<int:project_id>/boq.pdf', views_print.boq_pdf, name='boq_pdf'),
    path('api/project/<int:project_id>/boq/phases/', api_views.boq_phase_create, name='api_boq_phase_create'),
    path('api/project/<int:project_id>/boq/recalculate-weights/', api_views.boq_recalculate_weights, name='api_boq_recalculate_weights'),
    path('api/project/<int:project_id>/boq/phases/<int:phase_id>/', api_views.boq_phase_update_delete, name='api_boq_phase_update_delete'),
    path('api/project/<int:project_id>/boq/phases/<int:phase_id>/sub-items/', api_views.boq_subitem_create, name='api_boq_subitem_create'),
    path('api/project/<int:project_id>/boq/sub-items/<int:subitem_id>/', api_views.boq_subitem_update_delete, name='api_boq_subitem_update_delete'),
    path('api/project/<int:project_id>/boq/sub-items/<int:subitem_id>/progress/', api_views.boq_progress_entry_create, name='api_boq_progress_entry_create'),
    path('project/<int:project_id>/schedule/', views.project_schedule, name='project_schedule'),
    path('project/<int:project_id>/plan-vs-actual/', views.plan_vs_actual_page, name='plan_vs_actual'),
    path('project/<int:project_id>/schedule/edit/', views.schedule_editor, name='schedule_editor'),
    path('project/<int:project_id>/milestones/', views.milestone_editor, name='milestone_editor'),
    path('api/project/<int:project_id>/milestones/phases/<int:phase_id>/', api_views.milestone_create, name='api_milestone_create'),
    path('api/project/<int:project_id>/milestones/<int:milestone_id>/', api_views.milestone_update_delete, name='api_milestone_update_delete'),
]
