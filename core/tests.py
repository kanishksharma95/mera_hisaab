from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership
from expenses.models import Expense, ExpenseCategory
from sales.models import Sale, SaleItem

User = get_user_model()


def make_shop(email, name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    return user, business


class DashboardTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("d@shop.com", "Shop")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    def test_dashboard_renders(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics", resp.context)


class ReportsTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("rep@shop.com", "Shop")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()
        # One sale: revenue 1180 (incl 180 tax), net 1000, COGS 600 -> gross 400.
        sale = Sale.objects.create(
            business=self.business, invoice_number="MH-1", subtotal=Decimal("1000"),
            order_discount=Decimal("0"), tax_total=Decimal("180"), total=Decimal("1180"),
            paid_amount=Decimal("1180"), due_amount=Decimal("0"),
            payment_status=Sale.PaymentStatus.PAID,
        )
        SaleItem.objects.create(
            business=self.business, sale=sale, product_name="Widget",
            quantity=Decimal("2"), unit_price=Decimal("500"), cost_price=Decimal("300"),
            tax_amount=Decimal("180"), line_total=Decimal("1180"),
        )
        cat = ExpenseCategory.objects.create(business=self.business, name="Rent")
        Expense.objects.create(business=self.business, category=cat, amount=Decimal("250"))

    def test_reports_render_and_pnl(self):
        resp = self.client.get(reverse("core:reports"), {"period": "month"})
        self.assertEqual(resp.status_code, 200)
        pnl = resp.context["pnl"]
        self.assertEqual(pnl["revenue"], Decimal("1180"))
        self.assertEqual(pnl["cogs"], Decimal("600"))
        self.assertEqual(pnl["gross_profit"], Decimal("400"))
        self.assertEqual(pnl["expenses"], Decimal("250"))
        self.assertEqual(pnl["net_profit"], Decimal("150"))
        self.assertEqual(pnl["tax"], Decimal("180"))

    def test_reports_top_products(self):
        resp = self.client.get(reverse("core:reports"), {"period": "month"})
        top = resp.context["top_products"]
        self.assertEqual(top[0]["product_name"], "Widget")
        self.assertEqual(top[0]["revenue"], Decimal("1180"))

    def test_reports_tenant_isolation(self):
        _, biz_b = make_shop("other@shop.com", "Other")
        Sale.objects.create(
            business=biz_b, invoice_number="X-1", subtotal=Decimal("9999"),
            total=Decimal("9999"), paid_amount=Decimal("9999"), due_amount=Decimal("0"),
            payment_status=Sale.PaymentStatus.PAID,
        )
        resp = self.client.get(reverse("core:reports"), {"period": "month"})
        # Only this shop's revenue is counted, never the other business's.
        self.assertEqual(resp.context["pnl"]["revenue"], Decimal("1180"))


class HealthzTests(TestCase):
    def test_healthz_returns_json_with_expected_keys(self):
        import json

        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["status"], "ok")
        self.assertIn("database", data)
        self.assertEqual(data["database"], "connected")
        self.assertIn("cache", data)
        self.assertIn("email", data)
        self.assertIn("razorpay", data)
