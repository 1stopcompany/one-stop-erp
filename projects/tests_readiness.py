"""
The readiness rule: no work on a project without valid insurance and a fully priced BOQ.
Covers the rule itself, that the SQL picker and the Python check agree, that every project-linked model is either
guarded or deliberately exempt, and the behaviour a user sees (blocked with a message; setup and fixing stay possible).
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase
from django.urls import reverse

from procurement.models import PurchaseRequisition
from reports.models import DailyReport, DailyWorkForce
from reports.progress_models import ProjectPhase, ProjectPhaseProgressEntry, ProjectPhaseSubItem
from timesheets.models import CheckInLocation, Employee

from . import guard, readiness
from .models import Project
from .testing import add_insurance, make_ready, price_boq

User = get_user_model()


def make_project(symbol="RDY", status="active", manager=None, engineer=None):
    return Project.objects.create(
        name=f"Project {symbol}", project_symbol=symbol, contract_number=f"C-{symbol}", client_name="Client",
        start_date=date(2025, 1, 1), status=status, manager=manager, site_engineer=engineer,
    )


class RuleTests(TestCase):
    def codes(self, project):
        return sorted({p.code for p in readiness.check(project).problems})

    def test_an_empty_active_project_is_blocked_for_insurance_and_boq(self):
        self.assertEqual(self.codes(make_project()), ["boq", "insurance"])

    def test_planning_is_blocked_even_when_everything_else_is_in_place(self):
        project = make_ready(make_project(status="planning"))
        self.assertEqual(self.codes(project), ["startup"])

    def test_insurance_must_exist_be_unexpired_and_have_a_document(self):
        project = price_boq(make_project()).project
        self.assertEqual(self.codes(project), ["insurance"])
        add_insurance(project, days=-1)
        self.assertIn("expired", readiness.check(project).summary())
        project.insurances.all().delete()
        add_insurance(project, document="")
        self.assertIn("no document", readiness.check(project).summary())
        project.insurances.all().delete()
        add_insurance(project)
        self.assertTrue(readiness.check(project).ok)

    def test_a_policy_that_expires_later_blocks_the_project_again(self):
        project = make_ready(make_project())
        self.assertTrue(readiness.check(project).ok)
        project.insurances.update(end_date=date.today() - timedelta(days=1))
        self.assertEqual(self.codes(project), ["insurance"])

    def test_boq_must_exist(self):
        project = make_project()
        add_insurance(project)
        self.assertIn("no BOQ", readiness.check(project).summary())

    def test_every_item_needs_quantity_and_both_prices(self):
        project = make_project()
        add_insurance(project)
        phase = ProjectPhase.objects.create(project=project, code="1", name_ar="a", weight_percentage=0, order=1)
        good = ProjectPhaseSubItem.objects.create(phase=phase, code="1.1", name_ar="ok", weight_percentage=0,
                                                  quantity=Decimal("5"), budget_unit_price=Decimal("2"), contract_unit_price=Decimal("3"))
        self.assertTrue(readiness.check(project).ok)
        for field, value in [("quantity", None), ("quantity", Decimal("0")), ("budget_unit_price", Decimal("0")), ("contract_unit_price", Decimal("0"))]:
            bad = ProjectPhaseSubItem.objects.create(phase=phase, code="9.9", name_ar="bad", weight_percentage=0,
                                                     quantity=Decimal("5"), budget_unit_price=Decimal("2"), contract_unit_price=Decimal("3"))
            setattr(bad, field, value)
            bad.save()
            problems = readiness.check(project).problems
            self.assertEqual([p.code for p in problems], ["boq"], (field, value))
            self.assertIn("9.9", problems[0].detail)
            bad.delete()
        self.assertTrue(readiness.check(project).ok)
        good.delete()

    def test_a_phase_without_items_blocks(self):
        project = make_ready(make_project())
        ProjectPhase.objects.create(project=project, code="2", name_ar="empty", weight_percentage=0, order=2)
        problems = readiness.check(project).problems
        self.assertEqual([p.code for p in problems], ["boq"])
        self.assertIn("no priced item", problems[0].message)

    def test_closed_projects_are_not_subject_to_the_rule(self):
        for status in ("completed", "archived"):
            self.assertTrue(readiness.check(make_project(f"C{status[:2]}", status=status)).ok)

    def test_the_sql_picker_agrees_with_the_python_check(self):
        projects = {
            "empty": make_project("EMP"),
            "planning": make_ready(make_project("PLN", status="planning")),
            "ready": make_ready(make_project("OK")),
            "no_insurance": price_boq(make_project("NI")).project,
            "no_boq": add_insurance(make_project("NB")).project,
            "expired": price_boq(add_insurance(make_project("EXP"), days=-3).project).project,
            "no_document": price_boq(add_insurance(make_project("NDC"), document="").project).project,
            "closed": make_project("CLS", status="completed"),
            "on_hold_ready": make_ready(make_project("OHR", status="on_hold")),
        }
        empty_phase = make_ready(make_project("EPH"))
        ProjectPhase.objects.create(project=empty_phase, code="2", name_ar="x", weight_percentage=0, order=2)
        projects["empty_phase"] = empty_phase
        unpriced = make_ready(make_project("UNP"))
        ProjectPhaseSubItem.objects.filter(phase__project=unpriced).update(contract_unit_price=0)
        projects["unpriced"] = unpriced

        expected = {name for name, p in projects.items() if readiness.check(p).ok}
        actual = {name for name, p in projects.items() if readiness.ready_projects().filter(pk=p.pk).exists()}
        self.assertEqual(actual, expected)
        self.assertEqual(expected, {"ready", "closed", "on_hold_ready"})


class GuardCoverageTests(TestCase):
    def test_every_project_linked_model_is_guarded_or_deliberately_exempt(self):
        linked = set()
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, models.ForeignKey) and field.related_model is Project:
                    linked.add(model._meta.label)
        unclassified = linked - set(guard.GUARDED) - guard.EXEMPT
        self.assertFalse(unclassified, f"Decide for each: add to projects/guard.py GUARDED (work) or EXEMPT (setup): {sorted(unclassified)}")

    def test_the_lists_only_name_real_models_and_real_paths(self):
        for label in guard.EXEMPT:
            apps.get_model(label)
        for label, path in guard.GUARDED.items():
            model = apps.get_model(label)
            self.assertNotIn(label, guard.EXEMPT)
            for option in path.split("|"):
                current = model
                for name in option.split("."):
                    field = current._meta.get_field(name)
                    current = field.related_model
                self.assertIs(current, Project, f"{label}: '{option}' doesn't lead to a Project")


class EnforcementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")
        cls.admin = User.objects.create_user("adm", password="x", role="admin", is_superuser=True)
        cls.blocked = make_project("BLK", manager=cls.pm, engineer=cls.engineer)
        cls.ready = make_ready(make_project("GO", manager=cls.pm, engineer=cls.engineer))

    def daily(self, project):
        return DailyReport.objects.create(project=project, site_engineer=self.engineer, weather_conditions="clear")

    def test_nothing_is_blocked_outside_a_web_request(self):
        self.daily(self.blocked)        # a management command, the shell, a test: not enforced
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_inside_a_request_work_on_a_blocked_project_is_refused(self):
        with readiness.request_scope():
            with self.assertRaises(readiness.ProjectNotReady) as ctx:
                self.daily(self.blocked)
            self.assertIn("Work on 'Project BLK' is blocked", str(ctx.exception))
            self.assertIn("insurance", str(ctx.exception))
            self.assertIn("BOQ", str(ctx.exception))
            self.daily(self.ready)      # a ready project is fine
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_children_and_progress_are_refused_too(self):
        report = self.daily(self.blocked)
        sub = ProjectPhaseSubItem.objects.create(phase=ProjectPhase.objects.create(project=self.blocked, code="1", name_ar="a", weight_percentage=0),
                                                 name_ar="s", weight_percentage=0)
        with readiness.request_scope():
            with self.assertRaises(readiness.ProjectNotReady):
                DailyWorkForce.objects.create(report=report, category="skilled", count=3)
            with self.assertRaises(readiness.ProjectNotReady):
                ProjectPhaseProgressEntry.objects.create(sub_item=sub, report_date=date.today(), execution_percentage=10)
            with self.assertRaises(readiness.ProjectNotReady):
                PurchaseRequisition.objects.create(project=self.blocked, required_date=date.today(), requested_by=self.engineer)

    def test_a_gps_check_in_counts_as_work_on_its_project(self):
        check_in = CheckInLocation(employee=Employee(pk=999), project=self.blocked, latitude=31.0, longitude=35.0, check_type="check_in")
        with readiness.request_scope():
            with self.assertRaises(readiness.ProjectNotReady):
                check_in.save()
        self.assertFalse(CheckInLocation.objects.exists())

    def test_setup_records_are_never_blocked(self):
        with readiness.request_scope():
            phase = ProjectPhase.objects.create(project=self.blocked, code="1", name_ar="setup", weight_percentage=0, order=1)
            ProjectPhaseSubItem.objects.create(phase=phase, name_ar="line", weight_percentage=0)
            add_insurance(self.blocked)
            self.blocked.tender_documents.create(category="contract", title="T", document="tender/x.pdf")
            self.blocked.name = "Renamed"
            self.blocked.save()

    def test_suspended_switches_it_off_explicitly(self):
        with readiness.request_scope(), readiness.suspended():
            self.daily(self.blocked)

    def test_fixing_the_project_unblocks_it(self):
        with readiness.request_scope():
            with self.assertRaises(readiness.ProjectNotReady):
                self.daily(self.blocked)
            make_ready(self.blocked)
            self.daily(self.blocked)

    def test_closed_projects_can_still_be_written_to(self):
        closed = make_project("CLD", status="completed")
        with readiness.request_scope():
            self.daily(closed)


class WebBehaviourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")
        cls.admin = User.objects.create_user("adm", password="x", role="admin", is_superuser=True)
        cls.blocked = make_project("BLK", manager=cls.pm, engineer=cls.engineer)
        cls.ready = make_ready(make_project("GO", manager=cls.pm, engineer=cls.engineer))
        cls.report = DailyReport.objects.create(project=cls.blocked, site_engineer=cls.engineer, weather_conditions="clear")

    def add_workforce(self, report):
        self.client.force_login(self.engineer)
        return self.client.post(reverse("reports:api_add_workforce", args=[report.pk]), {"category": "skilled", "designation": "x", "count": "2"})

    def test_ajax_add_on_a_blocked_project_is_refused_with_the_reason(self):
        response = self.add_workforce(self.report)
        self.assertGreaterEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("is blocked", response.json()["message"])
        self.assertEqual(DailyWorkForce.objects.count(), 0)

    def test_ajax_add_works_once_the_project_is_ready(self):
        report = DailyReport.objects.create(project=self.ready, site_engineer=self.engineer, weather_conditions="clear")
        self.assertEqual(self.add_workforce(report).status_code, 200)
        self.assertEqual(DailyWorkForce.objects.count(), 1)
        make_ready(self.blocked)
        self.assertEqual(self.add_workforce(self.report).status_code, 200)

    def test_a_page_action_is_redirected_to_the_workflow_page_with_a_message(self):
        pr = PurchaseRequisition.objects.create(project=self.blocked, required_date=date.today(), requested_by=self.engineer)
        pr.lines.create(item=self._item(), quantity_requested=5, unit="bag")
        self.client.force_login(self.engineer)
        response = self.client.post(reverse("procurement:pr_submit", args=[pr.pk]), follow=True)
        self.assertRedirects(response, reverse("projects:workflow", args=[self.blocked.pk]))
        self.assertContains(response, "is blocked")
        pr.refresh_from_db()
        self.assertEqual(pr.status, "draft")

    def _item(self):
        from procurement.models import ItemMaster
        return ItemMaster.objects.create(aa_level="01", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="001",
                                         description="Cement", unit="bag")

    def test_json_clients_get_a_403_with_the_message(self):
        pr = PurchaseRequisition.objects.create(project=self.blocked, required_date=date.today(), requested_by=self.engineer)
        pr.lines.create(item=self._item(), quantity_requested=5, unit="bag")
        self.client.force_login(self.engineer)
        response = self.client.post(reverse("procurement:pr_submit", args=[pr.pk]), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["blocked"])
        self.assertIn("insurance", response.json()["error"])

    def test_the_project_pages_explain_why_and_say_nothing_when_ready(self):
        self.client.force_login(self.admin)
        for name in ("projects:project_detail", "projects:workflow"):
            page = self.client.get(reverse(name, args=[self.blocked.pk]))
            self.assertContains(page, "Work is blocked on this project", msg_prefix=name)
            self.assertContains(page, "No insurance policy is on file", msg_prefix=name)
            self.assertNotContains(self.client.get(reverse(name, args=[self.ready.pk])), "Work is blocked on this project", msg_prefix=name)
        listing = self.client.get(reverse("projects:project_list"))
        self.assertContains(listing, "Work blocked", count=1)

    def test_setup_pages_still_work_on_a_blocked_project(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("projects:workflow", args=[self.blocked.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("reports:boq_editor", args=[self.blocked.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("projects:insurance_add", args=[self.blocked.pk])).status_code, 200)

    def test_blocked_projects_are_not_offered_in_pickers(self):
        from procurement.forms import PurchaseRequisitionForm
        from procurement.forms_warehouse import ReorderForm, StockIssueForm
        for form in (PurchaseRequisitionForm(), ReorderForm(), StockIssueForm()):
            offered = set(form.fields["project"].queryset)
            self.assertIn(self.ready, offered)
            self.assertNotIn(self.blocked, offered)

    def test_a_report_form_cannot_pick_a_blocked_project(self):
        self.client.force_login(self.admin)
        before = DailyReport.objects.count()
        response = self.client.post(reverse("reports:daily_report_create"), {"project": self.blocked.pk, "weather_conditions": "clear", "remarks": ""})
        self.assertEqual(DailyReport.objects.count(), before)
        self.assertEqual(response.status_code, 200, "the form is shown again with an error, nothing is saved")
