from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership
from payments.models import Payment, PaymentMethod

from .models import Expense, ExpenseCategory
from .services import ensure_default_categories, record_expense

User = get_user_model()


def make_shop(email, name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=name)
    BusinessMembership.objects.create(user=user, business=business, role="owner")
    return user, business


class DefaultCategoryTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("e@shop.com", "Shop")

    def test_seeds_defaults_once(self):
        ensure_default_categories(self.business)
        first = ExpenseCategory.objects.for_business(self.business).count()
        self.assertGreater(first, 0)
        ensure_default_categories(self.business)  # idempotent
        self.assertEqual(
            ExpenseCategory.objects.for_business(self.business).count(), first
        )


class RecordExpenseTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("r@shop.com", "R")
        self.cat = ExpenseCategory.objects.create(business=self.business, name="Rent")
        self.cash = PaymentMethod.objects.create(
            business=self.business, name="Cash", code="cash"
        )

    def test_expense_creates_cashbook_out_payment(self):
        exp = record_expense(
            business=self.business, category=self.cat, amount=Decimal("5000"),
            method=self.cash, note="Shop rent", user=self.user,
        )
        self.assertEqual(exp.amount, Decimal("5000.00"))
        pay = Payment.objects.for_business(self.business).filter(
            reference=f"expense:{exp.id}"
        ).first()
        self.assertIsNotNone(pay)
        self.assertEqual(pay.direction, Payment.Direction.OUT)
        self.assertEqual(pay.amount, Decimal("5000.00"))

    def test_expense_without_method_records_no_payment(self):
        exp = record_expense(
            business=self.business, category=self.cat, amount=Decimal("100"),
        )
        self.assertEqual(Payment.objects.for_business(self.business).count(), 0)
        self.assertEqual(Expense.objects.for_business(self.business).count(), 1)

    def test_non_positive_rejected(self):
        with self.assertRaises(ValueError):
            record_expense(business=self.business, category=self.cat, amount=Decimal("0"))


class ExpenseViewTests(TestCase):
    def setUp(self):
        self.user, self.business = make_shop("v@shop.com", "V")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_business_id"] = self.business.id
        s.save()

    def test_list_seeds_and_renders(self):
        resp = self.client.get(reverse("expenses:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ExpenseCategory.objects.for_business(self.business).exists())

    def test_create_expense_scoped(self):
        cat = ExpenseCategory.objects.create(business=self.business, name="Transport")
        method = PaymentMethod.objects.create(
            business=self.business, name="UPI", code="upi"
        )
        self.client.post(reverse("expenses:add"), {
            "category": cat.pk, "amount": "250", "method": method.pk,
            "spent_on": "2026-09-01", "note": "Auto fare",
        })
        exp = Expense.objects.get(note="Auto fare")
        self.assertEqual(exp.business, self.business)
        self.assertEqual(exp.amount, Decimal("250.00"))

    def test_duplicate_category_rejected(self):
        self.client.post(reverse("expenses:category_add"), {"name": "Rent"})
        self.client.post(reverse("expenses:category_add"), {"name": "rent"})
        self.assertEqual(
            ExpenseCategory.objects.for_business(self.business)
            .filter(name__iexact="rent").count(),
            1,
        )

    def test_cannot_edit_other_business_category(self):
        _, biz_b = make_shop("b@shop.com", "B")
        cat_b = ExpenseCategory.objects.create(business=biz_b, name="X")
        resp = self.client.get(reverse("expenses:category_edit", args=[cat_b.pk]))
        self.assertEqual(resp.status_code, 404)
