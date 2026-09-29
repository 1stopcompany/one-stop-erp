# Generated manually: seeds Position.default_labor_classification for the site-relevant
# positions that have (or need) a matching Daily Report trade, so an HR employee with one of
# these positions gets their trade pre-filled automatically when picked for worker attendance.

from django.db import migrations


# (Position.title, WorkforceCategory.name, LaborClassification.name) -- the classification is
# created if it doesn't already exist (e.g. "Site Engineer" has no matching trade yet), reused
# if it does (e.g. "Project Manager", "Office Engineer" were already seeded).
POSITION_TRADE_MAP = [
    ('Site Engineer', 'Project Management', 'Site Engineer'),
    ('Project Manager', 'Project Management', 'Project Manager'),
    ('Office Engineer', 'Project Management', 'Office Engineer'),
]


def seed_mapping(apps, schema_editor):
    Position = apps.get_model('timesheets', 'Position')
    WorkforceCategory = apps.get_model('reports', 'WorkforceCategory')
    LaborClassification = apps.get_model('reports', 'LaborClassification')

    for position_title, category_name, trade_name in POSITION_TRADE_MAP:
        position = Position.objects.filter(title=position_title).first()
        if not position:
            continue
        category, _ = WorkforceCategory.objects.get_or_create(
            name=category_name, defaults={'is_staff_category': True}
        )
        classification, _ = LaborClassification.objects.get_or_create(
            category=category, name=trade_name
        )
        position.default_labor_classification = classification
        position.save(update_fields=['default_labor_classification'])


def unseed_mapping(apps, schema_editor):
    Position = apps.get_model('timesheets', 'Position')
    Position.objects.filter(
        title__in=[title for title, _, _ in POSITION_TRADE_MAP]
    ).update(default_labor_classification=None)


class Migration(migrations.Migration):

    dependencies = [
        ('timesheets', '0017_position_default_labor_classification'),
    ]

    operations = [
        migrations.RunPython(seed_mapping, unseed_mapping),
    ]
