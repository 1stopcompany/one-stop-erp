from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CoreRoutingTests(TestCase):
    """Regression tests for the main ERP routes and module dashboards."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(
            username="stage2-admin",
            password="Stage2-Test-Password!",
            role="admin",
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_authenticated_module_pages_render(self):
        route_names = [
            "dashboard",
            "accounts:dashboard",
            "accounts:user_list",
            "accounts:user_create",
            "accounts:user_profile",
            "projects:project_list",
            "projects:project_create",
            "reports:daily_report_list",
            "reports:monthly_report_list",
            "procurement:dashboard",
            "procurement:item_list",
            "procurement:item_create",
            "procurement:pr_list",
            "procurement:pr_create",
            "procurement:po_list",
            "procurement:po_create",
            "procurement:vendor_list",
            "procurement:vendor_create",
            "procurement:receipt_list",
            "procurement:receipt_create",
            "cost_control:dashboard",
            "cost_control:budget_list",
            "cost_control:budget_create",
            "cost_control:forecast_list",
            "cost_control:forecast_create",
            "cost_control:report_list",
            "cost_control:report_create",
            "cost_control:alert_list",
            "timesheets:dashboard",
            "timesheets:employee_list",
            "timesheets:employee_add",
            "timesheets:department_list",
            "timesheets:department_add",
            "timesheets:position_list",
            "timesheets:position_add",
            "timesheets:location_tracking",
            "timesheets:geofence_list",
            "timesheets:geofence_add",
            "timesheets:attendance_map",
            "crm:dashboard",
            "accounting:dashboard",
            "safety:dashboard",
            "equipment:dashboard",
            "subcontractors:dashboard",
            "blueprints:dashboard",
        ]

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{route_name} returned {response.status_code}",
                )

    def test_home_redirects_authenticated_user_to_dashboard(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("dashboard"))


class AnonymousAccessTests(TestCase):
    def test_home_redirects_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("accounts:login"))

    def test_protected_pages_do_not_allow_anonymous_access(self):
        route_names = [
            "dashboard",
            "projects:project_list",
            "procurement:dashboard",
            "procurement:item_create",
            "cost_control:dashboard",
            "crm:dashboard",
            "accounting:dashboard",
            "safety:dashboard",
            "equipment:dashboard",
            "subcontractors:dashboard",
            "blueprints:dashboard",
        ]
        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 302)
