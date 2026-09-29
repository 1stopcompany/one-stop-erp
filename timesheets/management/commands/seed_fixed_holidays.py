"""
Seed the fixed-date public holidays (same calendar date every year) for a
given year: New Year's Day, Labour Day, and Palestinian Independence Day.

The Islamic-calendar holidays (Eid al-Fitr, Eid al-Adha) shift every year
by the lunar calendar and are announced by moon sighting -- they are NOT
seeded here and must be entered by hand in the Holiday admin once the
dates for that year are confirmed.

Usage:
    python manage.py seed_fixed_holidays --year 2027
    python manage.py seed_fixed_holidays            # defaults to the current year
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from timesheets.models import Holiday

FIXED_HOLIDAYS = [
    (1, 1, "New Year's Day"),
    (5, 1, "Labour Day"),
    (11, 15, "Independence Day"),
]


class Command(BaseCommand):
    help = "Seed the fixed-date public holidays for a given year (New Year, Labour Day, Independence Day)"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None, help="Year to seed (default: current year)")

    def handle(self, *args, **options):
        year = options["year"] or timezone.localdate().year
        created_count = 0
        for month, day, name in FIXED_HOLIDAYS:
            holiday, created = Holiday.objects.get_or_create(date=date(year, month, day), defaults={"name": name})
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created {holiday}"))
            else:
                self.stdout.write(f"Already exists: {holiday}")
        self.stdout.write(self.style.SUCCESS(
            f"Done -- {created_count} new holiday(s) for {year}. "
            "Remember to add Eid al-Fitr and Eid al-Adha by hand once announced."
        ))
