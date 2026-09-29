from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import UserAuditLog


class AuthenticationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "Valid-Test-Password!"
        cls.user = get_user_model().objects.create_user(
            username="test-engineer",
            password=cls.password,
            role="site_engineer",
            first_name="Test",
            last_name="Engineer",
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login_redirects_to_erp_dashboard_and_is_audited(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(
            UserAuditLog.objects.filter(user=self.user, action="login").exists()
        )

    def test_invalid_login_stays_on_login_page(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_is_post_only_and_is_audited(self):
        self.client.force_login(self.user)
        get_response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(post_response, reverse("accounts:login"))
        self.assertTrue(
            UserAuditLog.objects.filter(user=self.user, action="logout").exists()
        )
