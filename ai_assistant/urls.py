from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("project/<int:project_id>/", views.project_ai, name="project_ai"),
    path("project/<int:project_id>/analyze/", views.analyze, name="analyze"),
    path("project/<int:project_id>/review/", views.start_review, name="start_review"),
    path("run/<int:run_id>/", views.run_detail, name="run_detail"),
    path("run/<int:run_id>/status/", views.run_status, name="run_status"),
    path("run/<int:run_id>/import/", views.run_import, name="run_import"),
    path("revision/<int:revision_id>/analyze/", views.analyze_drawing, name="analyze_drawing"),
    path("run/<int:run_id>/takeoff.csv", views.run_takeoff_csv, name="takeoff_csv"),
    path("project/<int:project_id>/edge/", views.project_edge, name="project_edge"),
    path("project/<int:project_id>/edge.csv", views.project_edge_csv, name="project_edge_csv"),
    path("chat/config/", views.chat_config, name="chat_config"),
    path("chat/message/", views.chat_message, name="chat_message"),
]
