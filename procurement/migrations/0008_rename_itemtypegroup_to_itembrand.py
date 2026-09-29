import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Renames ItemTypeGroup -> ItemBrand (matching the source workbook's
    own Family -> Group -> Classification -> Brand -> item terminology,
    per the client) and its FK related_name item_types -> brands.
    RenameModel preserves the existing table and data; only the Python
    name and the one related_name change.
    """

    dependencies = [
        ("procurement", "0007_itemfamily_itemgroup_itemclassification_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="ItemTypeGroup", new_name="ItemBrand"),
        migrations.AlterField(
            model_name="itembrand",
            name="classification",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="brands",
                to="procurement.itemclassification",
            ),
        ),
    ]
