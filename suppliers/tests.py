from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership

from .models import Supplier
from .services import record_bill, record_payment

User = get_user_model()


def make_shop(email, name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    return user, business


class SupplierLedgerTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("s@shop.com", "Shop")
        self.supplier = Supplier.objects.create(business=self.business, name="Wholesaler")

    def test_bill_increases_payable(self):
        record_bill(supplier=self.supplier, amount=Decimal("5000"))
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.current_balance, Decimal("5000.00"))

    def test_payment_reduces_payable(self):
        record_bill(supplier=self.supplier, amount=Decimal("5000"))
        record_payment(supplier=self.supplier, amount=Decimal("2000"), method="Cash")
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.current_balance, Decimal("3000.00"))

    def test_non_positive_rejected(self):
        with self.assertRaises(ValueError):
            record_bill(supplier=self.supplier, amount=Decimal("0"))


class SupplierViewTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("v@shop.com", "V")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    def test_create_supplier_scoped(self):
        self.client.post(reverse("suppliers:add"), {"name": "ABC Traders"})
        sup = Supplier.objects.get(name="ABC Traders")
        self.assertEqual(sup.business, self.business)

    def test_cannot_view_other_business_supplier(self):
        _, biz_b = make_shop("b@shop.com", "B")
        sup_b = Supplier.objects.create(business=biz_b, name="Other")
        resp = self.client.get(reverse("suppliers:detail", args=[sup_b.pk]))
        self.assertEqual(resp.status_code, 404)
