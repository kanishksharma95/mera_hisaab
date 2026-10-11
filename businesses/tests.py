from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.middleware import SESSION_KEY

from .models import Business, BusinessMembership, BusinessType

User = get_user_model()


class OnboardingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@shop.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_login(self.user)

    def test_default_business_types_seeded(self):
        # Data migration should have created the default catalog.
        self.assertTrue(BusinessType.objects.filter(name="Mobile").exists())
        mobile = BusinessType.objects.get(name="Mobile")
        self.assertTrue(mobile.fields.filter(name="IMEI", required=True).exists())

    def test_onboarding_creates_business_and_owner_membership(self):
        bt = BusinessType.objects.get(name="Grocery")
        resp = self.client.post(
            reverse("businesses:onboarding"),
            {
                "name": "Sharma General Store",
                "business_type": bt.id,
                "currency": "INR",
                "default_tax_percent": "0",
            },
        )
        self.assertRedirects(resp, reverse("core:dashboard"))
        business = Business.objects.get(name="Sharma General Store")
        membership = BusinessMembership.objects.get(user=self.user, business=business)
        self.assertEqual(membership.role, BusinessMembership.Role.OWNER)
        # Active business is set in the session.
        self.assertEqual(self.client.session[SESSION_KEY], business.id)

    def test_owner_name_defaults_to_user_full_name(self):
        resp = self.client.post(
            reverse("businesses:onboarding"),
            {"name": "No Owner Name Shop", "currency": "INR", "default_tax_percent": "0"},
        )
        self.assertEqual(resp.status_code, 302)
        business = Business.objects.get(name="No Owner Name Shop")
        self.assertEqual(business.owner_name, "Owner")


class TenantIsolationTests(TestCase):
    """The critical multi-tenant guarantee: users only reach their own data."""

    def setUp(self):
        self.user_a = User.objects.create_user(email="a@shop.com", password="pw!23456X")
        self.user_b = User.objects.create_user(email="b@shop.com", password="pw!23456X")
        self.biz_a = Business.objects.create(name="Business A")
        self.biz_b = Business.objects.create(name="Business B")
        BusinessMembership.objects.create(
            user=self.user_a, business=self.biz_a, role=BusinessMembership.Role.OWNER
        )
        BusinessMembership.objects.create(
            user=self.user_b, business=self.biz_b, role=BusinessMembership.Role.OWNER
        )

    def test_middleware_sets_only_own_business(self):
        self.client.force_login(self.user_a)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.wsgi_request.business, self.biz_a)

    def test_cannot_switch_to_foreign_business(self):
        """User A must NOT be able to switch into Business B."""
        self.client.force_login(self.user_a)
        resp = self.client.post(
            reverse("businesses:switch_business", args=[self.biz_b.id])
        )
        self.assertEqual(resp.status_code, 404)
        # Session must not have been changed to the foreign business.
        self.assertNotEqual(self.client.session.get(SESSION_KEY), self.biz_b.id)

    def test_can_switch_to_own_business(self):
        # Give user A a second legitimate membership.
        biz_c = Business.objects.create(name="Business C")
        BusinessMembership.objects.create(
            user=self.user_a, business=biz_c, role=BusinessMembership.Role.MANAGER
        )
        self.client.force_login(self.user_a)
        resp = self.client.post(
            reverse("businesses:switch_business", args=[biz_c.id])
        )
        self.assertRedirects(resp, reverse("core:dashboard"))
        self.assertEqual(self.client.session[SESSION_KEY], biz_c.id)

    def test_stale_session_business_is_cleared(self):
        """If the session points at a business the user can't access, drop it."""
        self.client.force_login(self.user_a)
        session = self.client.session
        session[SESSION_KEY] = self.biz_b.id  # forge a foreign id
        session.save()
        resp = self.client.get(reverse("core:dashboard"))
        # Middleware falls back to the user's real business, not the forged one.
        self.assertEqual(resp.wsgi_request.business, self.biz_a)

    def test_for_business_queryset_scoping(self):
        """The tenant manager helper filters strictly by business."""
        a_only = BusinessMembership.objects.for_business(self.biz_a)
        self.assertTrue(all(m.business_id == self.biz_a.id for m in a_only))
        self.assertFalse(a_only.filter(business=self.biz_b).exists())


class BusinessRequiredRedirectTests(TestCase):
    def test_user_without_business_redirected_to_onboarding(self):
        user = User.objects.create_user(email="new@shop.com", password="pw!23456X")
        self.client.force_login(user)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(resp, reverse("businesses:onboarding"))


class RoleBasedAccessControlTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@test.com", password="pw!123456")
        self.cashier = User.objects.create_user(email="cashier@test.com", password="pw!123456")
        self.accountant = User.objects.create_user(email="accountant@test.com", password="pw!123456")

        self.biz = Business.objects.create(name="Test Retail Shop")
        self.m_owner = BusinessMembership.objects.create(
            user=self.owner, business=self.biz, role=BusinessMembership.Role.OWNER
        )
        self.m_cashier = BusinessMembership.objects.create(
            user=self.cashier, business=self.biz, role=BusinessMembership.Role.CASHIER
        )
        self.m_accountant = BusinessMembership.objects.create(
            user=self.accountant, business=self.biz, role=BusinessMembership.Role.ACCOUNTANT
        )
        from payments.models import BusinessSubscription
        BusinessSubscription.objects.create(
            business=self.biz,
            plan_code="pro_monthly",
            status=BusinessSubscription.Status.ACTIVE,
        )


    def test_owner_can_view_team_list_and_add_cashier(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("businesses:team_list"))
        self.assertEqual(resp.status_code, 200)

        post_resp = self.client.post(
            reverse("businesses:employee_create"),
            {
                "email": "newcashier@test.com",
                "full_name": "New Cashier",
                "phone": "9876543210",
                "role": "cashier",
                "password": "Password123!",
            },
        )
        self.assertRedirects(post_resp, reverse("businesses:team_list"))
        self.assertTrue(User.objects.filter(email="newcashier@test.com").exists())
        self.assertTrue(
            BusinessMembership.objects.filter(
                user__email="newcashier@test.com", business=self.biz, role="cashier"
            ).exists()
        )

    def test_cashier_cannot_access_team_management(self):
        self.client.force_login(self.cashier)
        resp = self.client.get(reverse("businesses:team_list"))
        self.assertEqual(resp.status_code, 403)

    def test_cashier_cannot_access_reports(self):
        self.client.force_login(self.cashier)
        resp = self.client.get(reverse("core:reports"))
        self.assertEqual(resp.status_code, 403)

    def test_accountant_can_access_reports(self):
        self.client.force_login(self.accountant)
        resp = self.client.get(reverse("core:reports"))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_update_role_and_delete_employee(self):
        self.client.force_login(self.owner)
        edit_url = reverse("businesses:employee_edit", args=[self.m_cashier.id])
        edit_resp = self.client.post(
            edit_url,
            {"role": "manager", "is_active": True},
        )
        self.assertRedirects(edit_resp, reverse("businesses:team_list"))
        self.m_cashier.refresh_from_db()
        self.assertEqual(self.m_cashier.role, "manager")

        delete_url = reverse("businesses:employee_delete", args=[self.m_cashier.id])
        del_resp = self.client.post(delete_url)
        self.assertRedirects(del_resp, reverse("businesses:team_list"))
        self.assertFalse(BusinessMembership.objects.filter(id=self.m_cashier.id).exists())

