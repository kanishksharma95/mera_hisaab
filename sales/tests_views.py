import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership
from customers.models import Customer
from payments.services import ensure_default_methods
from payments.models import PaymentMethod
from products.models import Product

from .models import Sale

User = get_user_model()


def shop(email, name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    ensure_default_methods(business)
    return user, business


def login_as(client, user, business):
    client.force_login(user)
    s = client.session
    s["active_business_id"] = business.id
    s.save()


class PosViewTests(TestCase):
    def setUp(self):
        self.user, self.business = shop("a@shop.com", "A Store")
        login_as(self.client, self.user, self.business)
        self.product = Product.objects.create(
            business=self.business, name="Milk", selling_price=Decimal("30"),
            purchase_price=Decimal("24"), current_stock=Decimal("50"),
        )

    def test_pos_renders_and_seeds_payment_methods(self):
        resp = self.client.get(reverse("sales:pos"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PaymentMethod.objects.for_business(self.business).exists())

    def test_search_returns_only_own_products(self):
        resp = self.client.get(reverse("sales:pos_search"), {"q": "Milk"})
        data = resp.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Milk")

    def test_checkout_creates_sale_and_returns_redirect(self):
        cash = PaymentMethod.objects.for_business(self.business).get(code="cash")
        body = {
            "items": [{"product": self.product.id, "quantity": 3, "unit_price": "30"}],
            "payments": [{"method": cash.id, "amount": "90"}],
        }
        resp = self.client.post(
            reverse("sales:pos_checkout"), data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        sale = Sale.objects.get(invoice_number=payload["invoice_number"])
        self.assertEqual(sale.total, Decimal("90.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("47.000"))

    def test_checkout_rejects_credit_without_customer(self):
        credit = PaymentMethod.objects.for_business(self.business).get(code="credit")
        body = {
            "items": [{"product": self.product.id, "quantity": 1, "unit_price": "30"}],
            "payments": [{"method": credit.id, "amount": "30"}],
        }
        resp = self.client.post(
            reverse("sales:pos_checkout"), data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("customer", resp.json()["error"].lower())
        self.assertEqual(Sale.objects.count(), 0)

    def test_pos_context_includes_quick_actions(self):
        resp = self.client.get(reverse("sales:pos"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("top_products", resp.context)
        self.assertIn("default_cash_method_id", resp.context)
        self.assertIn("default_credit_method_id", resp.context)
        self.assertTrue(resp.context["default_cash_method_id"])
        self.assertTrue(resp.context["default_credit_method_id"])

    def test_quick_cash_walkin_customer_deducts_stock(self):
        # Initial stock: 50
        cash = PaymentMethod.objects.for_business(self.business).get(code="cash")
        body = {
            "items": [{"product": self.product.id, "quantity": 3, "unit_price": "30"}],
            "customer": None,
            "payments": [{"method": cash.id, "amount": "90"}],
        }
        resp = self.client.post(
            reverse("sales:pos_checkout"), data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["total_amount"], "90.00")

        sale = Sale.objects.get(invoice_number=data["invoice_number"])
        self.assertIsNone(sale.customer)
        self.assertEqual(sale.paid_amount, Decimal("90.00"))
        self.assertEqual(sale.due_amount, Decimal("0.00"))

        # Verify stock deducted: 50 - 3 = 47
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("47.000"))

    def test_quick_cash_regular_customer_records_under_customer(self):
        customer = Customer.objects.create(
            business=self.business, name="Ramesh Kumar", phone="9876543210"
        )
        cash = PaymentMethod.objects.for_business(self.business).get(code="cash")
        body = {
            "items": [{"product": self.product.id, "quantity": 2, "unit_price": "30"}],
            "customer": customer.id,
            "payments": [{"method": cash.id, "amount": "60"}],
        }
        resp = self.client.post(
            reverse("sales:pos_checkout"), data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        sale = Sale.objects.get(invoice_number=data["invoice_number"])
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.paid_amount, Decimal("60.00"))
        self.assertEqual(sale.due_amount, Decimal("0.00"))

        # Customer's purchase history has this sale
        self.assertIn(sale, customer.sales.all())
        # Stock: 50 - 2 = 48
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("48.000"))

    def test_quick_credit_regular_customer_udhaar_updates_balance(self):
        customer = Customer.objects.create(
            business=self.business, name="Sharma Ji", phone="9123456780"
        )
        credit = PaymentMethod.objects.for_business(self.business).get(code="credit")
        body = {
            "items": [{"product": self.product.id, "quantity": 5, "unit_price": "30"}],
            "customer": customer.id,
            "payments": [{"method": credit.id, "amount": "150"}],
        }
        resp = self.client.post(
            reverse("sales:pos_checkout"), data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        sale = Sale.objects.get(invoice_number=data["invoice_number"])
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.paid_amount, Decimal("0.00"))
        self.assertEqual(sale.due_amount, Decimal("150.00"))
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNPAID)

        # Customer balance updated: +150
        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal("150.00"))

        # Stock deducted: 50 - 5 = 45
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("45.000"))


class InvoiceViewTests(TestCase):
    def setUp(self):
        self.user, self.business = shop("a@shop.com", "A Store")
        login_as(self.client, self.user, self.business)
        self.product = Product.objects.create(
            business=self.business, name="Pen", selling_price=Decimal("10"),
            current_stock=Decimal("100"),
        )
        from .services import create_sale
        cash = PaymentMethod.objects.for_business(self.business).get(code="cash")
        self.sale = create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.product, "quantity": 2}],
            payments=[{"method": cash, "amount": Decimal("20")}],
        )

    def test_invoice_page_renders(self):
        resp = self.client.get(reverse("sales:invoice", args=[self.sale.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.sale.invoice_number)

    def test_pdf_generates(self):
        resp = self.client.get(reverse("sales:invoice_pdf", args=[self.sale.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_public_invoice_accessible_without_login(self):
        anon = self.client_class()  # fresh, unauthenticated client
        resp = anon.get(reverse("public_invoice", args=[self.sale.public_token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.sale.invoice_number)


class InvoiceIsolationTests(TestCase):
    def test_cannot_open_other_business_invoice(self):
        user_a, biz_a = shop("a@x.com", "A")
        user_b, biz_b = shop("b@x.com", "B")
        product_b = Product.objects.create(business=biz_b, name="X", selling_price=Decimal("10"), current_stock=5)
        from .services import create_sale
        cash_b = PaymentMethod.objects.for_business(biz_b).get(code="cash")
        sale_b = create_sale(
            business=biz_b, user=user_b, items=[{"product": product_b, "quantity": 1}],
            payments=[{"method": cash_b, "amount": Decimal("10")}],
        )
        login_as(self.client, user_a, biz_a)
        resp = self.client.get(reverse("sales:invoice", args=[sale_b.pk]))
        self.assertEqual(resp.status_code, 404)
