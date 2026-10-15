from django.db import migrations

# The last claim number already used per series, read from the company's payment folders (1.11 Payments) when the claim form moved into the system.
# The next claim of each series continues after it. Wrong? Edit "Payment claim numbering" in the admin site.
SERIES = [
    # prefix, separator, digits, last number, project symbol (if different from the prefix)
    ('MAIN OFFICE SUP', '-', 4, 14, ''),
    ('GPR', '-', 3, 7, ''),
    ('ORL', '-', 3, 5, ''),
    ('ORW', '-', 3, 16, ''),
    ('TAB', '-', 3, 9, ''),
    ('YAN', '.', 3, 4, 'YCN'),
    ('QROOF', '-', 3, 0, ''),
    ('QSM', '-', 3, 0, ''),
]


def seed(apps, schema_editor):
    Sequence = apps.get_model('accounting', 'PaymentClaimSequence')
    for prefix, separator, digits, last, symbol in SERIES:
        Sequence.objects.get_or_create(prefix=prefix, defaults={'separator': separator, 'digits': digits, 'last_number': last, 'project_symbol': symbol})


class Migration(migrations.Migration):

    dependencies = [('accounting', '0001_payment_claims')]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
