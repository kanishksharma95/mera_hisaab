from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from businesses.models import Business, BusinessMembership
from customers.models import Customer
from inventory.models import InventoryTransaction
from payments.models import Payment, PaymentMethod
from payments.services import ensure_default_methods
from products.models import Product

from .models import Sale
from .services import create_sale

User = get_user_model()


def setup_shop(email="s@shop.com", name="Shop", include_tax=False):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name, prices_include_tax=include_tax)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    ensure_default_methods(business)
    return user, business


def method(business, code):
    return PaymentMethod.objects.for_business(business).get(code=code)


class BillingTotalsTests(TestCase):
    def setUp(self):
        self.user, self.business = setup_shop()
        self.p = Product.objects.create(
            business=self.business, name="T-Shirt", purchase_price=Decimal("300"),
            selling_price=Decimal("500"), tax_percent=Decimal("0"), current_stock=Decimal("10"),
        )

    def test_totals_no_tax_full_cash(self):
        sale = create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.p, "quantity": 2}],
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("1000")}],
        )
        self.assertEqual(sale.subtotal, Decimal("1000.00"))
        self.assertEqual(sale.total, Decimal("1000.00"))
        self.assertEqual(sale.paid_amount, Decimal("1000.00"))
        self.assertEqual(sale.due_amount, Decimal("0.00"))
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.PAID)

    def test_tax_exclusive_calculation(self):
        self.p.tax_percent = Decimal("18")
        self.p.save()
        sale = create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.p, "quantity": 1}],
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("590")}],
        )
        self.assertEqual(sale.subtotal, Decimal("500.00"))
        self.assertEqual(sale.tax_total, Decimal("90.00"))
        self.assertEqual(sale.total, Decimal("590.00"))

    def test_tax_inclusive_calculation(self):
        _, biz = setup_shop(email="inc@shop.com", name="Inc", include_tax=True)
        BusinessMembership.objects.filter(business=biz)
        prod = Product.objects.create(
            business=biz, name="Item", purchase_price=Decimal("50"),
            selling_price=Decimal("118"), tax_percent=Decimal("18"), current_stock=Decimal("5"),
        )
        user = User.objects.get(email="inc@shop.com")
        sale = create_sale(
            business=biz, user=user, items=[{"product": prod, "quantity": 1}],
            payments=[{"method": method(biz, "cash"), "amount": Decimal("118")}],
        )
        # 118 incl. 18% -> net 100, tax 18
        self.assertEqual(sale.subtotal, Decimal("100.00"))
        self.assertEqual(sale.tax_total, Decimal("18.00"))
        self.assertEqual(sale.total, Decimal("118.00"))

    def test_line_and_order_discount(self):
        sale = create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.p, "quantity": 2, "discount": Decimal("100")}],
            order_discount=Decimal("50"),
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("850")}],
        )
        # 2*500=1000 - 100 line disc = 900 subtotal; -50 order disc = 850 total
        self.assertEqual(sale.subtotal, Decimal("900.00"))
        self.assertEqual(sale.discount_total, Decimal("150.00"))
        self.assertEqual(sale.total, Decimal("850.00"))


class BillingStockTests(TestCase):
    def setUp(self):
        self.user, self.business = setup_shop()
        self.p = Product.objects.create(
            business=self.business, name="Rice", selling_price=Decimal("60"),
            purchase_price=Decimal("40"), current_stock=Decimal("20"),
        )

    def test_sale_decrements_stock_and_logs_movement(self):
        create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.p, "quantity": 5}],
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("300")}],
        )
        self.p.refresh_from_db()
        self.assertEqual(self.p.current_stock, Decimal("15.000"))
        txn = InventoryTransaction.objects.get(product=self.p, kind="sale")
        self.assertEqual(txn.quantity, Decimal("-5.000"))
        self.assertEqual(txn.balance_after, Decimal("15.000"))

    def test_gross_profit_from_cost_snapshot(self):
        sale = create_sale(
            business=self.business, user=self.user,
            items=[{"product": self.p, "quantity": 5}],
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("300")}],
        )
        # revenue 300 - COGS (40*5=200) = 100
        self.assertEqual(sale.gross_profit, Decimal("100.00"))


class BillingCreditTests(TestCase):
    def setUp(self):
        self.user, self.business = setup_shop()
        self.customer = Customer.objects.create(business=self.business, name="Aman")
        self.p = Product.objects.create(
            business=self.business, name="Item", selling_price=Decimal("500"),
            purchase_price=Decimal("300"), current_stock=Decimal("10"),
        )

    def test_partial_payment_posts_udhaar(self):
        sale = create_sale(
            business=self.business, user=self.user, customer=self.customer,
            items=[{"product": self.p, "quantity": 2}],  # total 1000
            payments=[{"method": method(self.business, "cash"), "amount": Decimal("400")}],
        )
        self.assertEqual(sale.paid_amount, Decimal("400.00"))
        self.assertEqual(sale.due_amount, Decimal("600.00"))
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.PARTIAL)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("600.00"))

    def test_full_credit_requires_customer(self):
        with self.assertRaises(ValidationError):
            create_sale(
                business=self.business, user=self.user, customer=None,
                items=[{"product": self.p, "quantity": 1}],
                payments=[],  # nothing paid, no customer
            )

    def test_no_payment_row_for_credit_method(self):
        create_sale(
            business=self.business, user=self.user, customer=self.customer,
            items=[{"product": self.p, "quantity": 1}],
            payments=[{"method": method(self.business, "credit"), "amount": Decimal("500")}],
        )
        # Credit is not a cash Payment; it should be udhaar instead.
        self.assertEqual(Payment.objects.count(), 0)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("500.00"))


class BillingIsolationTests(TestCase):
    def test_cannot_bill_another_shops_product(self):
        user_a, biz_a = setup_shop(email="a@x.com", name="A")
        _, biz_b = setup_shop(email="b@x.com", name="B")
        prod_b = Product.objects.create(business=biz_b, name="B-item", selling_price=Decimal("10"))
        with self.assertRaises(ValidationError):
            create_sale(
                business=biz_a, user=user_a,
                items=[{"product": prod_b, "quantity": 1}],
                payments=[{"method": method(biz_a, "cash"), "amount": Decimal("10")}],
            )

    def test_invoice_numbers_are_sequential_per_business(self):
        user_a, biz_a = setup_shop(email="a@x.com", name="A")
        p = Product.objects.create(business=biz_a, name="X", selling_price=Decimal("10"), current_stock=100)
        nums = []
        for _ in range(3):
            s = create_sale(
                business=biz_a, user=user_a, items=[{"product": p, "quantity": 1}],
                payments=[{"method": method(biz_a, "cash"), "amount": Decimal("10")}],
            )
            nums.append(s.invoice_number)
        self.assertTrue(nums[0].endswith("000001"))
        self.assertTrue(nums[1].endswith("000002"))
        self.assertTrue(nums[2].endswith("000003"))
