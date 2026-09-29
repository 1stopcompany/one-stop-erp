from django.conf import settings
from django.db import models

from projects.models import Project


def ai_upload_path(instance, filename):
    return f"ai_uploads/{instance.project_id}/{filename}"


class AIRun(models.Model):
    """
    One job handed to the AI assistant for a project: reading a document into a draft BOQ, or
    reviewing the whole project. Nothing the AI produces is applied on its own -- `result` is a draft
    or a report that a person looks at first (a draft BOQ is imported only when someone presses
    Import; see ai_assistant.importer).
    """
    BOQ_EXTRACT = "boq_extract"
    DRAWING_TAKEOFF = "drawing_takeoff"
    PROJECT_REVIEW = "project_review"
    KINDS = [
        (BOQ_EXTRACT, "Read a document into a draft BOQ"),
        (DRAWING_TAKEOFF, "Materials, quantities and green-building data"),
        (PROJECT_REVIEW, "Project review"),
    ]

    PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
    STATUSES = [(PENDING, "Waiting"), (RUNNING, "Working"), (DONE, "Done"), (FAILED, "Failed")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ai_runs")
    kind = models.CharField(max_length=20, choices=KINDS)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)

    # ---- what was read (BOQ extraction)
    source_label = models.CharField(max_length=255, blank=True)
    source_file = models.FileField(upload_to=ai_upload_path, blank=True, help_text="A file uploaded straight to the assistant")
    source_tender = models.ForeignKey("projects.ProjectTenderDocument", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    source_revision = models.ForeignKey("blueprints.BlueprintRevision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    instructions = models.TextField(blank=True, help_text="Anything the reader should know, e.g. 'the quantities are in section 3 only'")

    # ---- outcome
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    model_name = models.CharField(max_length=60, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)

    # ---- import of a draft BOQ
    imported_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    import_summary = models.JSONField(null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ai_runs")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_finished(self):
        return self.status in (self.DONE, self.FAILED)

    def __str__(self):
        return f"{self.get_kind_display()} - {self.project.project_symbol} ({self.get_status_display()})"
