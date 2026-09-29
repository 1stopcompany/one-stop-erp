"""Feeds subcontractor (Musana'a) agreement spend into project_cost_summary (cost_control/services.py),
so a signed agreement counts as committed/actual cost against its BOQ items exactly like a PO does."""
from decimal import Decimal

from .models import SubcontractorAgreement

ZERO = Decimal("0")

# A draft agreement isn't committed yet; a terminated one no longer counts.
COMMITTED_STATUSES = ["active", "completed"]


def spending_by_sub_item(project):
    """
    (committed, actual) as {sub_item_id: value}, matching procurement.services.spending_by_sub_item's
    shape so cost_control can merge the two.

    Committed = each line's own value. Actual = payments made so far, split across an agreement's
    lines in proportion to their share of its total value -- a Musana'a payment is normally certified
    against progress of the whole scope, not booked against one BOQ line at a time.
    """
    committed, actual = {}, {}
    agreements = SubcontractorAgreement.objects.filter(project=project, status__in=COMMITTED_STATUSES).prefetch_related("lines")
    for agreement in agreements:
        paid = agreement.paid_to_date
        total = agreement.total_value
        for line in agreement.lines.all():
            committed[line.sub_item_id] = committed.get(line.sub_item_id, ZERO) + line.total_price
            if total > 0:
                actual[line.sub_item_id] = actual.get(line.sub_item_id, ZERO) + (paid * line.total_price / total)
    return committed, actual
