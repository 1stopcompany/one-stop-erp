from django.db import migrations
from django.utils import timezone

KEYS = ["insurance", "tender", "drawings"]


def backfill(apps, schema_editor):
    """Projects that are already running (anything but 'planning') skip the start-up flow: all stages complete."""
    Project = apps.get_model("projects", "Project")
    ProjectStage = apps.get_model("projects", "ProjectStage")
    now = timezone.now()
    for project in Project.objects.exclude(status="planning"):
        for key in KEYS:
            ProjectStage.objects.get_or_create(project=project, key=key, defaults={"completed_at": now})


class Migration(migrations.Migration):
    dependencies = [("projects", "0005_projectinsurance_projecttenderdocument_projectstage")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
