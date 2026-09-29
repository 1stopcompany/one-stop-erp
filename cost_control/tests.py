from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CostControlRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="cost-admin",
            password="Cost-Test-Password!",
            role="admin",
            is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_renders_without_project(self):
        response = self.client.get(reverse("cost_control:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cost Control Dashboard")

    def test_chart_routes_are_registered(self):
        self.assertEqual(
            reverse("cost_control:api_budget_vs_actual"),
            "/cost_control/api/charts/budget-vs-actual/",
        )
        self.assertEqual(
            reverse("cost_control:api_variance_analysis"),
            "/cost_control/api/charts/variance-analysis/",
        )

    def test_chart_endpoints_require_project_id(self):
        for route_name in (
            "cost_control:api_budget_vs_actual",
            "cost_control:api_variance_analysis",
        ):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], "project_id is required.")
