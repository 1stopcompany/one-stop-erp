from __future__ import annotations

from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import Budget, BudgetAlert, CostReport


@shared_task
def check_budget_overruns(threshold_pct: float = 10.0):
    """
    Raise an alert for every budget line whose cost is running over what the work done so
    far is worth (actual vs earned value), or that has ordered more than its whole budget.
    """
    from projects.models import Project
    from .services import project_cost_summary

    for project in Project.objects.filter(cost_budgets__isnull=False).distinct():
        for row in project_cost_summary(project)["lines"]:
            overrun_pct = ((row["actual"] - row["earned"]) / row["earned"] * 100) if row["earned"] else None
            over_committed = row["status"] == "over_committed"
            if not (over_committed or (overrun_pct is not None and overrun_pct >= threshold_pct)):
                continue
            pct = float(overrun_pct) if overrun_pct is not None else 0.0
            BudgetAlert.objects.get_or_create(
                project=project,
                budget=row["budget"],
                alert_type="overrun",
                is_resolved=False,
                defaults={
                    "severity": "critical" if pct >= 20 or over_committed else "high",
                    "message": (
                        f"Ordered {row['committed']} against a budget of {row['budget_total']}"
                        if over_committed else f"Cost is {pct:.1f}% above the value of the work done"
                    ),
                    "actual_value": row["actual"],
                    "threshold_value": row["earned"],
                },
            )


@shared_task
def generate_weekly_cost_reports():
    end = timezone.now().date()
    start = (timezone.now() - timedelta(days=7)).date()

    projects = Budget.objects.values_list("project_id", flat=True).distinct()
    for pid in projects:
        CostReport.objects.get_or_create(
            project_id=pid,
            report_type="weekly",
            period_start=start,
            defaults={"period_end": end},
        )
