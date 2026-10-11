import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership
from inventory.models import InventoryTransaction
from payments.models import Payment, PaymentMethod
from payments.services import ensure_default_methods
from products.models import Product
from suppliers.models import Supplier

from .models import Purchase
from .services import create_purchase

User = get_user_model()


def make_shop(email="p@shop.com", name="Shop"):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    ensure_default_methods(business)
    return user, business


def method(business, code):
    return PaymentMethod.objects.for_business(business).get(code=code)


class PurchaseServiceTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop()
        self.supplier = Supplier.objects.create(business=self.business, name="Wholesaler")
        self.product = Product.objects.create(
            business=self.business, name="Rice", purchase_price=Decimal("40"),
            selling_price=Decimal("55"), current_stock=Decimal("10"),
        )

    def test_purchase_increases_stock_and_logs_movement(self):
        create_purchase(
            business=self.business, user=self.user, supplier=self.supplier,
            items=[{"product": self.product, "quantity": 25, "unit_cost": "42"}],
            payments=[{"method": method(self.business, "cash"), "amount": "1050"}],
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("35.000"))
        txn = InventoryTransaction.objects.get(product=self.product, kind="purchase")
        self.assertEqual(txn.quantity, Decimal("25.000"))
        self.assertEqual(txn.balance_after, Decimal("35.000"))

    def test_purchase_updates_product_cost(self):
        create_purchase(
            business=self.business, user=self.user, supplier=self.supplier,
            items=[{"product": self.product, "quantity": 5, "unit_cost": "48"}],
            payments=[{"method": method(self.business, "cash"), "amount": "240"}],
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, Decimal("48.00"))

    def test_credit_purchase_creates_payable(self):
        purchase = create_purchase(
            business=self.business, user=self.user, supplier=self.supplier,
            items=[{"product": self.product, "quantity": 10, "unit_cost": "40"}],  # total 400
            payments=[{"method": method(self.business, "cash"), "amount": "150"}],
        )
        self.assertEqual(purchase.total, Decimal("400.00"))
        self.assertEqual(purchase.paid_amount, Decimal("150.00"))
        self.assertEqual(purchase.due_amount, Decimal("250.00"))
        self.assertEqual(purchase.payment_status, Purchase.PaymentStatus.PARTIAL)
        self.supplier.refresh_from_db()
        # payable = billed 400 − paid 150 = 250
        self.assertEqual(self.supplier.current_balance, Decimal("250.00"))

    def test_credit_without_supplier_rejected(self):
        with self.assertRaises(ValidationError):
            create_purchase(
                business=self.business, user=self.user, supplier=None,
                items=[{"product": self.product, "quantity": 1, "unit_cost": "40"}],
                payments=[],  # unpaid, no supplier
            )

    def test_tax_totals(self):
        purchase = create_purchase(
            business=self.business, user=self.user, supplier=self.supplier,
            items=[{"product": self.product, "quantity": 10, "unit_cost": "40", "tax_percent": "5"}],
            payments=[{"method": method(self.business, "cash"), "amount": "420"}],
        )
        self.assertEqual(purchase.subtotal, Decimal("400.00"))
        self.assertEqual(purchase.tax_total, Decimal("20.00"))
        self.assertEqual(purchase.total, Decimal("420.00"))

    def test_cannot_purchase_other_shops_product(self):
        _, biz_b = make_shop(email="b@shop.com", name="B")
        prod_b = Product.objects.create(business=biz_b, name="X", purchase_price=Decimal("1"))
        with self.assertRaises(ValidationError):
            create_purchase(
                business=self.business, user=self.user, supplier=self.supplier,
                items=[{"product": prod_b, "quantity": 1, "unit_cost": "1"}],
                payments=[{"method": method(self.business, "cash"), "amount": "1"}],
            )


class PurchaseViewTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop()
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()
        self.product = Product.objects.create(
            business=self.business, name="Sugar", purchase_price=Decimal("40"),
            selling_price=Decimal("50"), current_stock=Decimal("0"),
        )

    def test_checkout_creates_purchase_and_stock(self):
        cash = method(self.business, "cash")
        body = {
            "items": [{"product": self.product.id, "quantity": 20, "unit_cost": "40"}],
            "payments": [{"method": cash.id, "amount": "800"}],
        }
        resp = self.client.post(reverse("purchases:checkout"), data=json.dumps(body),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        num = resp.json()["number"]
        p = Purchase.objects.get(number=num)
        self.assertEqual(p.total, Decimal("800.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("20.000"))

    def test_purchase_numbers_sequential(self):
        cash = method(self.business, "cash")
        nums = []
        for _ in range(2):
            r = self.client.post(reverse("purchases:checkout"), data=json.dumps({
                "items": [{"product": self.product.id, "quantity": 1, "unit_cost": "40"}],
                "payments": [{"method": cash.id, "amount": "40"}],
            }), content_type="application/json")
            nums.append(r.json()["number"])
        self.assertTrue(nums[0].endswith("000001"))
        self.assertTrue(nums[1].endswith("000002"))
        self.assertTrue(nums[0].startswith("PUR-"))
