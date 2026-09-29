import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from blueprints.models import Blueprint, BlueprintRevision
from reports.schedule_models import ScheduleTask
from . import workflow
from .forms import ProjectForm
from .models import Project, ProjectInsurance, ProjectManagementPlan, ProjectStage
from .testing import make_ready, price_boq

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()


def pdf(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class WorkflowTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("adm", password="x", role="admin", is_superuser=True)
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.other_pm = User.objects.create_user("pm2", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")
        cls.project = Project.objects.create(
            name="Tower", project_symbol="TW", contract_number="C1", client_name="Client",
            start_date=date(2025, 1, 1), manager=cls.pm, site_engineer=cls.engineer, status="planning",
        )

    def add_insurance(self, end=None, days=365):
        return ProjectInsurance.objects.create(
            project=self.project, policy_type="car", insurer="Ins Co", policy_number="P-1",
            start_date=date.today() - timedelta(days=10), end_date=end or date.today() + timedelta(days=days),
            document=pdf(), uploaded_by=self.pm,
        )

    def add_tender(self):
        return self.project.tender_documents.create(category="contract", title="Contract", document=pdf(), uploaded_by=self.pm)

    def add_approved_drawing(self):
        bp = Blueprint.objects.create(project=self.project, drawing_number="A-01", title="Plan", discipline="architectural")
        return BlueprintRevision.objects.create(blueprint=bp, revision="0", file=pdf(), status="approved")

    def add_regulatory_approvals(self):
        for body in ("government", "municipality", "civil_defense"):
            self.project.regulatory_approvals.create(body=body, document=pdf(), uploaded_by=self.pm)

    def add_schedule_task(self):
        return ScheduleTask.objects.create(
            project=self.project, source_task_id=1, unique_id=1, name="A1", outline_level=1,
            start_date=date.today(), finish_date=date.today() + timedelta(days=5),
        )

    def add_management_plans(self, site_management_checklist_complete=True):
        for category, _label in ProjectManagementPlan.CATEGORIES:
            plan = self.project.management_plans.create(category=category, document=pdf(), uploaded_by=self.pm)
            if category == ProjectManagementPlan.SITE_MANAGEMENT and site_management_checklist_complete:
                for field in ProjectManagementPlan.CHECKLIST_FIELDS:
                    setattr(plan, field, True)
                plan.save()


class WorkflowRuleTests(WorkflowTestBase):
    def test_stages_start_locked_in_order(self):
        board = workflow.stage_board(self.project)
        self.assertEqual([r["key"] for r in board], ["insurance", "tender", "drawings", "schedule", "plans"])
        self.assertEqual([r["locked"] for r in board], [False, True, True, True, True])

    def test_cannot_complete_without_requirement(self):
        with self.assertRaises(workflow.WorkflowError):
            workflow.complete_stage(self.project, "insurance", self.pm)
        self.add_insurance(end=date.today() - timedelta(days=1))  # expired doesn't count
        with self.assertRaises(workflow.WorkflowError):
            workflow.complete_stage(self.project, "insurance", self.pm)

    def test_cannot_skip_ahead(self):
        self.add_tender()
        with self.assertRaises(workflow.WorkflowError):
            workflow.complete_stage(self.project, "tender", self.pm)

    def test_full_flow_starts_the_project(self):
        self.add_insurance()
        workflow.complete_stage(self.project, "insurance", self.pm)
        self.add_tender()
        workflow.complete_stage(self.project, "tender", self.pm)
        with self.assertRaises(workflow.WorkflowError):  # no approved drawing yet
            workflow.complete_stage(self.project, "drawings", self.pm)
        self.add_approved_drawing()
        with self.assertRaises(workflow.WorkflowError) as ctx:  # an approved drawing isn't enough: the BOQ must be priced
            workflow.complete_stage(self.project, "drawings", self.pm)
        self.assertIn("priced BOQ", str(ctx.exception))
        price_boq(self.project)
        with self.assertRaises(workflow.WorkflowError) as ctx:  # ...and government/municipality/civil defense approval is needed too
            workflow.complete_stage(self.project, "drawings", self.pm)
        self.assertIn("civil defense", str(ctx.exception))
        self.add_regulatory_approvals()
        workflow.complete_stage(self.project, "drawings", self.pm)

        with self.assertRaises(workflow.WorkflowError):  # no schedule imported yet
            workflow.complete_stage(self.project, "schedule", self.pm)
        self.add_schedule_task()
        workflow.complete_stage(self.project, "schedule", self.pm)

        with self.assertRaises(workflow.WorkflowError):  # management plans not uploaded yet
            workflow.complete_stage(self.project, "plans", self.pm)
        self.add_management_plans(site_management_checklist_complete=False)
        with self.assertRaises(workflow.WorkflowError) as ctx:  # site management's 6-point checklist isn't fully checked yet
            workflow.complete_stage(self.project, "plans", self.pm)
        self.assertIn("checklist", str(ctx.exception))
        site_plan = self.project.management_plans.get(category=ProjectManagementPlan.SITE_MANAGEMENT)
        for field in ProjectManagementPlan.CHECKLIST_FIELDS:
            setattr(site_plan, field, True)
        site_plan.save()
        workflow.complete_stage(self.project, "plans", self.pm)

        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "active")
        self.assertTrue(workflow.flow_complete(self.project))

    def test_running_projects_are_not_gated(self):
        legacy = Project.objects.create(
            name="Old", project_symbol="OLD", contract_number="C2", client_name="C", start_date=date(2024, 1, 1),
            manager=self.pm, status="active",
        )
        self.assertTrue(workflow.flow_complete(legacy))
        self.assertTrue(workflow.is_unlocked(legacy, "drawings"))

    def test_insurance_states(self):
        self.assertEqual(self.add_insurance(days=200).state, "valid")
        self.assertEqual(self.add_insurance(days=10).state, "expiring")
        self.assertEqual(self.add_insurance(end=date.today() - timedelta(days=3)).state, "expired")
        self.assertEqual(len(workflow.insurance_alerts([self.project])), 2)


class ProjectFormTests(WorkflowTestBase):
    def form_data(self, **extra):
        data = dict(name="New", project_symbol="NW", contract_number="C9", client_name="Client",
                    start_date="2025-01-01", maintenance_type="routine", manager=self.pm.pk)
        data.update(extra)
        return data

    def test_new_project_is_forced_to_planning(self):
        form = ProjectForm(self.form_data(status="active"))
        self.assertNotIn("status", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().status, "planning")

    def test_cannot_activate_before_flow_is_done(self):
        form = ProjectForm(self.form_data(status="active"), instance=self.project)
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_on_hold_is_still_allowed(self):
        self.assertTrue(ProjectForm(self.form_data(status="on_hold"), instance=self.project).is_valid())


class WorkflowViewTests(WorkflowTestBase):
    def test_permissions(self):
        url = reverse("projects:insurance_add", args=[self.project.pk])
        self.client.force_login(self.engineer)
        self.assertEqual(self.client.get(url).status_code, 403)        # site engineer can't manage
        self.assertEqual(self.client.get(reverse("projects:workflow", args=[self.project.pk])).status_code, 200)
        self.client.force_login(self.other_pm)
        self.assertEqual(self.client.get(reverse("projects:workflow", args=[self.project.pk])).status_code, 403)
        self.client.force_login(self.pm)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_tender_upload_is_locked_until_insurance_done(self):
        self.client.force_login(self.pm)
        resp = self.client.get(reverse("projects:tender_add", args=[self.project.pk]), follow=True)
        self.assertContains(resp, "locked")

    def test_upload_insurance_then_complete_stage(self):
        self.client.force_login(self.pm)
        resp = self.client.post(reverse("projects:insurance_add", args=[self.project.pk]), {
            "policy_type": "car", "insurer": "Ins", "policy_number": "9", "insured_amount": "1000",
            "start_date": "2025-01-01", "end_date": (date.today() + timedelta(days=100)).isoformat(),
            "document": pdf(),
        })
        self.assertRedirects(resp, reverse("projects:workflow", args=[self.project.pk]))
        self.client.post(reverse("projects:stage_complete", args=[self.project.pk, "insurance"]))
        self.assertTrue(self.project.stages.get(key="insurance").is_complete)

    def test_rejects_dangerous_file_type(self):
        self.client.force_login(self.pm)
        resp = self.client.post(reverse("projects:insurance_add", args=[self.project.pk]), {
            "policy_type": "car", "insurer": "Ins", "policy_number": "9",
            "start_date": "2025-01-01", "end_date": "2030-01-01",
            "document": SimpleUploadedFile("evil.exe", b"MZ"),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "files are not accepted")
        self.assertEqual(ProjectInsurance.objects.count(), 0)

    def test_documents_are_frozen_once_stage_complete(self):
        ins = self.add_insurance()
        workflow.complete_stage(self.project, "insurance", self.pm)
        self.client.force_login(self.pm)
        self.client.post(reverse("projects:insurance_delete", args=[self.project.pk, ins.pk]))
        self.assertTrue(ProjectInsurance.objects.filter(pk=ins.pk).exists())


class BlueprintTests(WorkflowTestBase):
    def open_drawings_stage(self):
        self.add_insurance()
        workflow.complete_stage(self.project, "insurance", self.pm)
        self.add_tender()
        workflow.complete_stage(self.project, "tender", self.pm)

    def upload(self, number="S-01", rev="0"):
        return self.client.post(reverse("blueprints:blueprint_add", args=[self.project.pk]), {
            "drawing_number": number, "title": "Foundation", "discipline": "structural",
            "revision": rev, "file": pdf("plan.pdf"), "notes": "",
        })

    def test_upload_locked_until_tender_done(self):
        self.client.force_login(self.pm)
        self.upload()
        self.assertEqual(Blueprint.objects.count(), 0)

    def test_upload_approve_supersede_reject(self):
        self.open_drawings_stage()
        self.client.force_login(self.engineer)  # own site engineer may upload...
        self.upload()
        rev0 = BlueprintRevision.objects.get()
        self.assertEqual(rev0.status, "pending")
        resp = self.client.post(reverse("blueprints:revision_review", args=[rev0.pk]), {"action": "approve"})
        self.assertEqual(resp.status_code, 403)  # ...but not approve

        self.client.force_login(self.pm)
        self.client.post(reverse("blueprints:revision_review", args=[rev0.pk]), {"action": "approve"})
        rev0.refresh_from_db()
        self.assertEqual(rev0.status, "approved")

        bp = rev0.blueprint
        self.client.post(reverse("blueprints:revision_add", args=[bp.pk]), {"revision": "A", "file": pdf("b.pdf"), "notes": ""})
        revA = bp.revisions.get(revision="A")
        self.client.post(reverse("blueprints:revision_review", args=[revA.pk]), {"action": "approve"})
        rev0.refresh_from_db()
        revA.refresh_from_db()
        self.assertEqual((rev0.status, revA.status), ("superseded", "approved"))
        self.assertEqual(bp.current_revision, revA)

        self.client.post(reverse("blueprints:revision_add", args=[bp.pk]), {"revision": "B", "file": pdf("c.pdf"), "notes": ""})
        revB = bp.revisions.get(revision="B")
        self.client.post(reverse("blueprints:revision_review", args=[revB.pk]), {"action": "reject", "reason": ""})
        revB.refresh_from_db()
        self.assertEqual(revB.status, "pending")  # a reason is required
        self.client.post(reverse("blueprints:revision_review", args=[revB.pk]), {"action": "reject", "reason": "Wrong level"})
        revB.refresh_from_db()
        self.assertEqual(revB.status, "rejected")

    def test_duplicate_drawing_number_is_refused(self):
        self.open_drawings_stage()
        self.client.force_login(self.pm)
        self.upload()
        self.upload()
        self.assertEqual(Blueprint.objects.count(), 1)

    def test_approved_drawing_unlocks_start_of_work(self):
        self.open_drawings_stage()
        self.client.force_login(self.pm)
        self.upload()
        rev = BlueprintRevision.objects.get()
        self.client.post(reverse("blueprints:revision_review", args=[rev.pk]), {"action": "approve"})
        price_boq(self.project)
        self.add_regulatory_approvals()
        self.client.post(reverse("projects:stage_complete", args=[self.project.pk, "drawings"]))
        self.assertTrue(self.project.stages.get(key="drawings").is_complete)
        self.assertTrue(workflow.is_unlocked(self.project, "schedule"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "planning")  # more stages remain (schedule, plans) before the project goes Active

        self.add_schedule_task()
        self.client.post(reverse("projects:stage_complete", args=[self.project.pk, "schedule"]))
        self.add_management_plans()
        self.client.post(reverse("projects:stage_complete", args=[self.project.pk, "plans"]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "active")


class ProjectPageButtonsTests(WorkflowTestBase):
    """The buttons at the top of the project page follow the role: a short toolbar, with BOQ/cost and print tools grouped in menus."""

    def setUp(self):
        # A ready project shows no red "blocked" banner, whose own buttons would muddy what the toolbar shows.
        Project.objects.filter(pk=self.project.pk).update(status="active")
        make_ready(self.project)

    def links(self, user):
        self.client.force_login(user)
        html = self.client.get(reverse("projects:project_detail", args=[self.project.pk])).content.decode()
        pk = self.project.pk
        return {
            "workflow": reverse("projects:workflow", args=[pk]) in html,
            "ai": reverse("ai_assistant:project_ai", args=[pk]) in html,
            "boq_menu": "BOQ &amp; Cost" in html,
            "manage_boq": reverse("reports:boq_editor", args=[pk]) in html,
            "budget": reverse("cost_control:budget_list") in html,
            "milestones": reverse("reports:milestone_editor", args=[pk]) in html,
            "print_boq": reverse("reports:boq_pdf", args=[pk]) in html,
            "print_cost": reverse("cost_control:report_pdf") in html,
            "edit": reverse("projects:project_edit", args=[pk]) in html,
        }

    def test_project_manager_sees_every_tool(self):
        shown = self.links(self.pm)
        self.assertTrue(all(shown.values()), shown)

    def test_general_manager_sees_only_view_and_print_tools(self):
        gm = User.objects.create_user("gm", password="x", role="general_manager")
        shown = self.links(gm)
        self.assertEqual({k for k, v in shown.items() if v}, {"workflow", "ai", "print_boq", "print_cost"})

    def test_site_engineer_only_gets_the_workflow_button(self):
        shown = self.links(self.engineer)
        self.assertEqual({k for k, v in shown.items() if v}, {"workflow"})


class DrawingUploadAnalysisTests(WorkflowTestBase):
    """Uploading a drawing hands it to the AI analysis (materials, quantities, green data) when that is switched on."""

    open_drawings_stage = BlueprintTests.open_drawings_stage
    upload = BlueprintTests.upload

    def test_a_new_drawing_is_handed_to_the_analysis(self):
        from unittest import mock

        self.open_drawings_stage()
        self.client.force_login(self.engineer)
        with mock.patch("ai_assistant.triggers.auto_analyze_revision", return_value=object()) as auto:
            response = self.upload()
        self.assertEqual(Blueprint.objects.count(), 1, "the upload itself is unaffected")
        auto.assert_called_once()
        self.assertEqual(auto.call_args.args[0], BlueprintRevision.objects.get())
        self.assertEqual(auto.call_args.args[1], self.engineer)
        text = " ".join(str(m) for m in response.wsgi_request._messages)
        self.assertIn("reading this drawing", text)

    def test_a_new_revision_is_handed_to_the_analysis_too(self):
        from unittest import mock

        self.open_drawings_stage()
        self.client.force_login(self.pm)
        self.upload()
        blueprint = Blueprint.objects.get()
        with mock.patch("ai_assistant.triggers.auto_analyze_revision", return_value=None) as auto:
            self.client.post(reverse("blueprints:revision_add", args=[blueprint.pk]), {"revision": "A", "file": pdf("plan2.pdf"), "notes": ""})
        self.assertEqual(BlueprintRevision.objects.count(), 2)
        auto.assert_called_once()
        self.assertEqual(auto.call_args.args[0].revision, "A")


class DrawingsGuideTests(WorkflowTestBase):
    def test_the_user_guide_is_a_pdf_and_is_linked_from_the_drawings_pages(self):
        self.client.force_login(self.pm)
        response = self.client.get(reverse("blueprints:manual_pdf"))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        for name, args in (("blueprints:dashboard", []), ("blueprints:project_drawings", [self.project.pk])):
            self.assertContains(self.client.get(reverse(name, args=args)), reverse("blueprints:manual_pdf"), msg_prefix=name)

    def test_the_guide_needs_a_login(self):
        self.assertEqual(self.client.get(reverse("blueprints:manual_pdf")).status_code, 302)
