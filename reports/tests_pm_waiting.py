from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project
from .models import DailyReport, MonthlyReport

User = get_user_model()


class ProjectManagerWaitingListTests(TestCase):
    """A project manager sees, on Site Reports, their projects' reports that are stuck with management."""

    @classmethod
    def setUpTestData(cls):
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.other_pm = User.objects.create_user("pm2", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")

        def project(symbol, manager):
            return Project.objects.create(
                name=f"Project {symbol}", project_symbol=symbol, contract_number=symbol, client_name="C",
                start_date=date(2025, 1, 1), manager=manager, site_engineer=cls.engineer, status="active",
            )

        cls.mine, cls.theirs = project("MINE", cls.pm), project("THEIRS", cls.other_pm)

        def daily(proj, status):
            return DailyReport.objects.create(
                project=proj, site_engineer=cls.engineer, weather_conditions="clear", status=status,
            )

        cls.waiting_review = daily(cls.mine, "submitted")
        cls.waiting_final = daily(cls.mine, "engineering_approved")
        cls.draft = daily(cls.mine, "draft")
        cls.approved = daily(cls.mine, "approved")
        cls.someone_elses = daily(cls.theirs, "submitted")

    def test_lists_only_my_projects_reports_that_are_waiting(self):
        self.client.force_login(self.pm)
        resp = self.client.get(reverse("reports:report_type_selection"))
        shown = [row["report"] for row in resp.context["awaiting_management"]]
        self.assertCountEqual(shown, [self.waiting_review, self.waiting_final])

    def test_says_who_it_is_waiting_for(self):
        self.client.force_login(self.pm)
        rows = {row["report"].pk: row["waiting_for"] for row in
                self.client.get(reverse("reports:report_type_selection")).context["awaiting_management"]}
        self.assertEqual(rows[self.waiting_review.pk], "Engineering manager review")
        self.assertEqual(rows[self.waiting_final.pk], "General manager final approval")

    def test_only_project_managers_get_the_list(self):
        self.client.force_login(self.engineer)
        resp = self.client.get(reverse("reports:report_type_selection"))
        self.assertNotIn("awaiting_management", resp.context)
