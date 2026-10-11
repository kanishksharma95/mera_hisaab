import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership
from customers.models import Customer
from sales.models import Sale

from .models import BusinessSubscription, Payment, PaymentMethod
from .services import (
    apply_gateway_payment_to_sale,
    ensure_default_methods,
)

User = get_user_model()


def make_shop(email, name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    return user, business


class DefaultMethodTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("m@shop.com", "Shop")

    def test_seeds_defaults_once(self):
        ensure_default_methods(self.business)
        first = PaymentMethod.objects.for_business(self.business).count()
        self.assertGreater(first, 0)
        # Idempotent — calling again does not duplicate.
        ensure_default_methods(self.business)
        self.assertEqual(
            PaymentMethod.objects.for_business(self.business).count(), first
        )


class PaymentViewTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("v@shop.com", "V")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    def test_method_list_seeds_and_renders(self):
        resp = self.client.get(reverse("payments:method_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PaymentMethod.objects.for_business(self.business).exists())

    def test_create_method_scoped_and_coded(self):
        self.client.post(reverse("payments:method_add"), {"name": "Paytm Wallet"})
        method = PaymentMethod.objects.get(name="Paytm Wallet")
        self.assertEqual(method.business, self.business)
        self.assertTrue(method.code)  # auto-derived, non-empty

    def test_duplicate_name_rejected(self):
        self.client.post(reverse("payments:method_add"), {"name": "Cash"})
        self.client.post(reverse("payments:method_add"), {"name": "cash"})
        self.assertEqual(
            PaymentMethod.objects.for_business(self.business)
            .filter(name__iexact="cash")
            .count(),
            1,
        )

    def test_toggle_deactivates(self):
        m = PaymentMethod.objects.create(
            business=self.business, name="Card", code="card"
        )
        self.client.post(reverse("payments:method_toggle", args=[m.pk]))
        m.refresh_from_db()
        self.assertFalse(m.is_active)

    def test_cannot_edit_other_business_method(self):
        _, biz_b = make_shop("b@shop.com", "B")
        m_b = PaymentMethod.objects.create(business=biz_b, name="X", code="x")
        resp = self.client.get(reverse("payments:method_edit", args=[m_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cashbook_totals_scoped(self):
        method = PaymentMethod.objects.create(
            business=self.business, name="Cash", code="cash"
        )
        Payment.objects.create(
            business=self.business, direction=Payment.Direction.IN,
            method=method, amount=Decimal("1000"),
        )
        Payment.objects.create(
            business=self.business, direction=Payment.Direction.OUT,
            method=method, amount=Decimal("400"),
        )
        # Another business's payment must not leak into totals.
        _, biz_b = make_shop("c@shop.com", "C")
        mb = PaymentMethod.objects.create(business=biz_b, name="Cash", code="cash")
        Payment.objects.create(
            business=biz_b, direction=Payment.Direction.IN,
            method=mb, amount=Decimal("9999"),
        )
        resp = self.client.get(reverse("payments:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["totals"]["total_in"], Decimal("1000"))
        self.assertEqual(resp.context["totals"]["total_out"], Decimal("400"))
        self.assertEqual(resp.context["totals"]["net"], Decimal("600"))


def make_credit_sale(business, customer, total="1000"):
    """A fully-unpaid sale whose balance sits as udhaar on the customer."""
    total = Decimal(total)
    customer.current_balance = total  # mimic the udhaar debit posted at sale time
    customer.save(update_fields=["current_balance"])
    return Sale.objects.create(
        business=business, invoice_number="MH-0001", customer=customer,
        subtotal=total, total=total, paid_amount=Decimal("0"),
        due_amount=total, payment_status=Sale.PaymentStatus.UNPAID,
    )


class GatewayPaymentTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("g@shop.com", "G")
        self.customer = Customer.objects.create(business=self.business, name="Ravi")
        self.sale = make_credit_sale(self.business, self.customer)

    def test_apply_records_payment_and_settles_sale(self):
        payment = apply_gateway_payment_to_sale(
            sale=self.sale, razorpay_payment_id="pay_1", razorpay_order_id="order_1",
        )
        self.sale.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("1000.00"))
        self.assertEqual(payment.method.code, "online")
        self.assertEqual(self.sale.paid_amount, Decimal("1000.00"))
        self.assertEqual(self.sale.due_amount, Decimal("0.00"))
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)
        # Udhaar cleared on the customer ledger.
        self.assertEqual(self.customer.current_balance, Decimal("0.00"))

    def test_apply_is_idempotent_on_replay(self):
        apply_gateway_payment_to_sale(sale=self.sale, razorpay_payment_id="pay_1")
        # Same payment id delivered again (webhook retry) must not double-count.
        apply_gateway_payment_to_sale(sale=self.sale, razorpay_payment_id="pay_1")
        self.assertEqual(
            Payment.objects.for_business(self.business)
            .filter(razorpay_payment_id="pay_1")
            .count(),
            1,
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal("1000.00"))


class WebhookTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("w@shop.com", "W")
        self.customer = Customer.objects.create(business=self.business, name="Sita")
        self.sale = make_credit_sale(self.business, self.customer)
        self.url = reverse("payments:razorpay_webhook")

    def _post(self, payload):
        return self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json",
            headers={"X-Razorpay-Signature": "sig"},
        )

    @mock.patch("payments.gateway.verify_webhook_signature", side_effect=Exception("bad"))
    def test_bad_signature_rejected(self, _verify):
        resp = self._post({"event": "payment.captured"})
        self.assertEqual(resp.status_code, 400)
        # Nothing recorded when the signature check fails.
        self.assertEqual(Payment.objects.count(), 0)

    @mock.patch("payments.gateway.verify_webhook_signature", return_value=None)
    def test_valid_payment_event_settles_sale(self, _verify):
        payload = {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "id": "pay_web1", "order_id": "order_web1", "amount": 100000,
                "notes": {"sale_id": str(self.sale.id)},
            }}},
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)
        self.assertTrue(
            Payment.objects.filter(razorpay_payment_id="pay_web1").exists()
        )


class InvoiceOrderTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("o@shop.com", "O")
        self.customer = Customer.objects.create(business=self.business, name="Amit")
        self.sale = make_credit_sale(self.business, self.customer)
        self.url = reverse("payments:invoice_order", args=[self.sale.public_token])

    @mock.patch("payments.gateway.is_configured", return_value=False)
    def test_order_blocked_when_gateway_disabled(self, _cfg):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 503)

    @mock.patch("payments.gateway.create_order")
    @mock.patch("payments.gateway.is_configured", return_value=True)
    def test_order_created_when_enabled(self, _cfg, mock_order):
        mock_order.return_value = {"id": "order_9", "amount": 100000, "currency": "INR"}
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["order_id"], "order_9")


class SubscriptionTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("sub@shop.com", "Sub")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    @mock.patch("payments.gateway.create_subscription")
    @mock.patch("payments.gateway.ensure_plan", return_value="plan_test")
    @mock.patch("payments.gateway.is_configured", return_value=True)
    def test_subscribe_creates_record_and_redirects(self, _cfg, _plan, mock_sub):
        mock_sub.return_value = {
            "id": "sub_test", "status": "created",
            "short_url": "https://rzp.io/i/test",
        }
        resp = self.client.post(reverse("payments:subscribe"), {"plan_code": "pro_monthly"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://rzp.io/i/test")
        sub = BusinessSubscription.objects.get(business=self.business)
        self.assertEqual(sub.razorpay_subscription_id, "sub_test")
        self.assertEqual(sub.plan_code, "pro_monthly")

    def test_subscription_status_synced_by_webhook(self):
        sub = BusinessSubscription.objects.create(
            business=self.business, plan_code="pro_monthly",
            razorpay_subscription_id="sub_sync", status="created",
        )
        payload = {
            "event": "subscription.activated",
            "payload": {"subscription": {"entity": {
                "id": "sub_sync", "status": "active", "current_end": 1893456000,
            }}},
        }
        with mock.patch("payments.gateway.verify_webhook_signature", return_value=None):
            resp = self.client.post(
                reverse("payments:razorpay_webhook"),
                data=json.dumps(payload), content_type="application/json",
                headers={"X-Razorpay-Signature": "sig"},
            )
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")
        self.assertIsNotNone(sub.current_period_end)


class SaaSLimitsAndSettingsTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("owner@biz.com", "Test Shop")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    def test_settings_view_get_and_post(self):
        resp = self.client.get(reverse("businesses:settings"))
        self.assertEqual(resp.status_code, 200)

        post_resp = self.client.post(
            reverse("businesses:settings"),
            {
                "name": "Updated Shop Name",
                "phone": "9998887776",
                "city": "Jaipur",
                "default_tax_percent": "18.00",
                "currency": "INR",
            },
        )
        self.assertRedirects(post_resp, reverse("businesses:settings"))
        self.business.refresh_from_db()
        self.assertEqual(self.business.name, "Updated Shop Name")
        self.assertEqual(self.business.city, "Jaipur")

    def test_thermal_receipt_renders(self):
        customer = Customer.objects.create(business=self.business, name="Raj")
        sale = make_credit_sale(self.business, customer, total="500")
        resp = self.client.get(reverse("sales:thermal", args=[sale.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Print Slip")
        self.assertContains(resp, "MH-0001")

    def test_csv_exports_return_200(self):
        sales_resp = self.client.get(reverse("sales:export_csv"))
        self.assertEqual(sales_resp.status_code, 200)
        self.assertEqual(sales_resp["Content-Type"], "text/csv")

        expense_resp = self.client.get(reverse("expenses:export_csv"))
        self.assertEqual(expense_resp.status_code, 200)
        self.assertEqual(expense_resp["Content-Type"], "text/csv")

        cust_resp = self.client.get(reverse("customers:export_csv"))
        self.assertEqual(cust_resp.status_code, 200)
        self.assertEqual(cust_resp["Content-Type"], "text/csv")

    def test_plan_limits_enforced_for_free_tier(self):
        from payments.limits import can_add_product, can_add_staff, is_pro_business

        self.assertFalse(is_pro_business(self.business))
        # Staff limit check: business already has 1 owner membership
        allowed, msg = can_add_staff(self.business)
        self.assertFalse(allowed)
        self.assertIn("Free plan allows only 1 user", msg)

