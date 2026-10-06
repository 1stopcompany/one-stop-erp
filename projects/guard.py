"""
Wires the readiness rule into the models: a pre_save guard on every OPERATIONAL record that belongs to a project.

Each entry maps a model to the attribute path that leads to its project. Adding a new operational model that
belongs to a project means adding one line here (tests in projects/tests_readiness.py fail if a model with a
direct link to Project is neither listed here nor deliberately exempt).

Not covered: bulk_create() and QuerySet.update() don't send pre_save, and deletes aren't blocked.
"""
import logging

from django.apps import apps
from django.db.models.signals import pre_save

from . import readiness

logger = logging.getLogger(__name__)

# Records that ARE the setup of a project. They must stay editable so a project can become ready.
EXEMPT = {
    "projects.Project", "projects.ProjectFloor", "projects.ProjectStage", "projects.ProjectInsurance",
    "projects.ProjectTenderDocument", "projects.ProjectRegulatoryApproval", "projects.ProjectManagementPlan",
    "blueprints.Blueprint", "blueprints.BlueprintRevision",
    "reports.ProjectPhase", "reports.ProjectPhaseSubItem", "reports.ProjectMilestone", "reports.ScheduleTask", "reports.ProjectSub",
    "ai_assistant.AIRun",
    # Not tied to a running project's work: the warehouse itself, and the older cost-control tables that nothing writes to.
    "procurement.Warehouse", "cost_control.Budget", "cost_control.CostForecast", "cost_control.CostReport", "cost_control.BudgetAlert",
    "timesheets.Employee", "timesheets.Geofence",
}

# model -> path to its project
GUARDED = {
    # daily / monthly / site / owner reports and everything typed into them
    "reports.DailyReport": "project", "reports.MonthlyReport": "project", "reports.SiteEvent": "project",
    "reports.OwnerFinancialReport": "project", "reports.ReportMaterialItem": "project",
    "reports.ReportAttachment": "site_event.project",
    "reports.DailyWorkForce": "report.project", "reports.DailyEquipment": "report.project", "reports.DailyActivity": "report.project",
    "reports.DailyMaterial": "report.project", "reports.DailyVisitor": "report.project",
    "reports.DailyReportWorkforceEntry": "report.project", "reports.DailyReportEquipmentEntry": "report.project",
    "reports.DailyReportMaterialEntry": "report.project", "reports.DailyReportWorkerAttendance": "report.project",
    "reports.DailyReportActivityProgress": "report.project", "reports.DailyReportQAQC": "report.project",
    "reports.DailyReportNextDayPlan": "report.project",
    "reports.FloorActivity": "report.project", "reports.ExternalWork": "report.project", "reports.MaterialSupply": "report.project",
    "reports.UpcomingWork": "report.project", "reports.MonthlyProgressCategoryItem": "report.project",
    "reports.MonthlyKeyActivity": "report.project", "reports.MonthlyIssueRiskDelay": "report.project",
    "reports.MonthlyReviewComment": "report.project", "reports.MonthlyWorkForce": "report.project",
    "reports.MonthlyEquipment": "report.project", "reports.MonthlyActivity": "report.project",
    "reports.OwnerReportPriceComparisonItem": "report.project", "reports.OwnerReportPhaseUpdate": "report.project",
    # progress and photos recorded against the BOQ
    "reports.ProjectPhaseProgressEntry": "sub_item.phase.project", "reports.ProjectPhasePhoto": "phase.project|daily_report.project|monthly_report.project|owner_financial_report.project",
    # purchasing, receiving and stock issued to a project
    "procurement.PurchaseRequisition": "project", "procurement.PurchaseRequisitionLine": "pr.project",
    "procurement.RequestForQuotation": "pr.project", "procurement.VendorQuote": "rfq.pr.project",
    "procurement.PurchaseOrder": "project", "procurement.PurchaseOrderLine": "po.project",
    "procurement.POReceipt": "po_line.po.project", "procurement.StockMovement": "project",
    # attendance: a GPS check-in counts toward a project
    "timesheets.CheckInLocation": "project",
    # a hand-typed wages entry (admin only; admins pass the guard anyway)
    "timesheets.DailyWorkerManualEntry": "project",
    # subcontractor (Musana'a) agreements and everything charged/paid through them
    "subcontractors.SubcontractorAgreement": "project",
    "subcontractors.SubcontractorAgreementLine": "agreement.project",
    "subcontractors.SubcontractorAgreementPayment": "agreement.project",
}


def _resolve(instance, path):
    """Follow "a.b.c" from the instance; several paths may be given as "a.b|c.d" (the first that leads somewhere wins).
    None if no path leads to a project (a nullable parent)."""
    for option in path.split("|"):
        obj = instance
        for name in option.split("."):
            obj = getattr(obj, name, None)
            if obj is None:
                break
        else:
            return obj
    return None


def _guard(sender, instance, raw=False, **kwargs):
    if raw or not readiness.enforcing():
        return
    path = GUARDED.get(sender._meta.label)
    if path:
        readiness.enforce(_resolve(instance, path))


def connect():
    for label in GUARDED:
        try:
            model = apps.get_model(label)
        except LookupError:
            logger.warning("Readiness guard: model %s doesn't exist any more; remove it from projects/guard.py", label)
            continue
        pre_save.connect(_guard, sender=model, dispatch_uid=f"project-readiness-{label}")
