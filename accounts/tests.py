from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserModelTests(TestCase):
    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_create_user_normalizes_and_hashes(self):
        user = User.objects.create_user(email="A@Example.com", password="pw12345x")
        # Domain part is normalized by Django.
        self.assertTrue(user.email.endswith("@example.com"))
        self.assertNotEqual(user.password, "pw12345x")
        self.assertTrue(user.check_password("pw12345x"))

    def test_create_superuser_flags(self):
        admin = User.objects.create_superuser(email="root@x.com", password="pw12345x")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class RegistrationFlowTests(TestCase):
    def test_registration_creates_user_and_redirects_to_onboarding(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Kanishk Sharma",
                "email": "kanishk@shop.com",
                "phone": "9876543210",
                "password1": "StrongPass!234",
                "password2": "StrongPass!234",
            },
        )
        self.assertRedirects(resp, reverse("businesses:onboarding"))
        user = User.objects.get(email="kanishk@shop.com")
        self.assertEqual(user.full_name, "Kanishk Sharma")
        self.assertEqual(user.phone, "9876543210")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(email="dup@shop.com", password="pw12345x")
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Someone",
                "email": "dup@shop.com",
                "phone": "1",
                "password1": "StrongPass!234",
                "password2": "StrongPass!234",
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with error
        self.assertEqual(User.objects.filter(email="dup@shop.com").count(), 1)

    def test_login_with_email(self):
        User.objects.create_user(email="log@shop.com", password="StrongPass!234")
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "log@shop.com", "password": "StrongPass!234"},
        )
        self.assertEqual(resp.status_code, 302)
