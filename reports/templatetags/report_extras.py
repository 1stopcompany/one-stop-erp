from django import template

register = template.Library()


@register.simple_tag
def pending_deletions_count():
    """Drafts that an engineer / manager deleted and the admin has not approved (or restored) yet, over the three report types."""
    from reports.models import DailyReport, MonthlyReport
    from reports.owner_financial_models import OwnerFinancialReport
    return sum(model.all_objects.filter(deleted_at__isnull=False).count() for model in (DailyReport, MonthlyReport, OwnerFinancialReport))
