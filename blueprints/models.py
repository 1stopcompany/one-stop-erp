from django.conf import settings
from django.db import models

from projects.models import Project
from projects.validators import validate_document_file


def _revision_upload_path(instance, filename):
    return f"project_docs/{instance.blueprint.project_id}/drawings/{instance.blueprint.drawing_number}/{filename}"


class Blueprint(models.Model):
    """One engineering drawing sheet of a project; its versions are BlueprintRevisions."""
    DISCIPLINES = [
        ("architectural", "Architectural"),
        ("structural", "Structural"),
        ("mechanical", "Mechanical"),
        ("electrical", "Electrical"),
        ("plumbing", "Plumbing"),
        ("civil", "Civil / site"),
        ("other", "Other"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="blueprints")
    drawing_number = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    discipline = models.CharField(max_length=20, choices=DISCIPLINES)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "drawing_number")
        ordering = ["discipline", "drawing_number"]

    @property
    def current_revision(self):
        """The revision to build from: the approved one, else the newest upload."""
        revisions = list(self.revisions.all())
        approved = [r for r in revisions if r.status == "approved"]
        pool = approved or revisions
        return max(pool, key=lambda r: r.uploaded_at) if pool else None

    def __str__(self):
        return f"{self.drawing_number} - {self.title}"


class BlueprintRevision(models.Model):
    """
    One uploaded version of a drawing. Only an 'approved' revision may be built from;
    approving a revision supersedes any earlier approved one of the same drawing.
    """
    STATUS = [
        ("pending", "Awaiting approval"),
        ("approved", "Approved for construction"),
        ("rejected", "Rejected"),
        ("superseded", "Superseded"),
    ]

    blueprint = models.ForeignKey(Blueprint, on_delete=models.CASCADE, related_name="revisions")
    revision = models.CharField(max_length=20, help_text="e.g. 0, A, B, R1")
    file = models.FileField(upload_to=_revision_upload_path, validators=[validate_document_file])
    notes = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("blueprint", "revision")
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.blueprint.drawing_number} rev {self.revision}"
