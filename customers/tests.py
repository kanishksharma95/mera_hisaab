from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership

from .models import Customer, CustomerLedgerEntry
from .services import record_charge, record_payment

User = get_user_model()


def make_user_with_business(email, business_name):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=business_name)
    BusinessMembership.objects.create(
        user=user, business=business, role=BusinessMembership.Role.OWNER
    )
    return user, business


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.user, self.business = make_user_with_business("a@shop.com", "A Store")
        self.customer = Customer.objects.create(business=self.business, name="Aman")

    def test_charge_increases_balance(self):
        record_charge(customer=self.customer, amount=Decimal("5000"), description="Sale")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("5000.00"))

    def test_payment_decreases_balance(self):
        record_charge(customer=self.customer, amount=Decimal("5000"))
        record_payment(customer=self.customer, amount=Decimal("2000"), method="Cash")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("3000.00"))
        # balance_after is tracked per row
        last = self.customer.ledger_entries.first()
        self.assertEqual(last.entry_type, CustomerLedgerEntry.EntryType.CREDIT)
        self.assertEqual(last.balance_after, Decimal("3000.00"))

    def test_full_payment_zeroes_balance(self):
        record_charge(customer=self.customer, amount=Decimal("1200"))
        record_payment(customer=self.customer, amount=Decimal("1200"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("0.00"))

    def test_overpayment_creates_advance(self):
        record_charge(customer=self.customer, amount=Decimal("1000"))
        record_payment(customer=self.customer, amount=Decimal("1500"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal("-500.00"))
        self.assertTrue(self.customer.is_advance)

    def test_non_positive_amount_rejected(self):
        with self.assertRaises(ValueError):
            record_payment(customer=self.customer, amount=Decimal("0"))


class CustomerViewTests(TestCase):
    def setUp(self):
        self.user, self.business = make_user_with_business("v@shop.com", "V Store")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_create_customer_scoped_to_business(self):
        self.client.post(reverse("customers:add"), {"name": "Rahul", "credit_limit": "0"})
        c = Customer.objects.get(name="Rahul")
        self.assertEqual(c.business, self.business)

    def test_create_customer_with_opening_balance(self):
        self.client.post(
            reverse("customers:add"),
            {"name": "Suresh", "credit_limit": "0", "opening_balance": "2500"},
        )
        c = Customer.objects.get(name="Suresh")
        self.assertEqual(c.current_balance, Decimal("2500.00"))
        entry = c.ledger_entries.first()
        self.assertEqual(entry.amount, Decimal("2500.00"))
        self.assertEqual(entry.description, "Pichla Udhaar / Opening Balance")

    def test_record_payment_via_view(self):
        c = Customer.objects.create(business=self.business, name="Simran")
        record_charge(customer=c, amount=Decimal("4800"))
        self.client.post(
            reverse("customers:payment", args=[c.pk]),
            {"amount": "800", "method": "UPI", "description": ""},
        )
        c.refresh_from_db()
        self.assertEqual(c.current_balance, Decimal("4000.00"))

    def test_add_udhaar_via_view(self):
        c = Customer.objects.create(business=self.business, name="Vikram")
        self.client.post(
            reverse("customers:add_udhaar", args=[c.pk]),
            {"amount": "1500", "description": "Groceries"},
        )
        c.refresh_from_db()
        self.assertEqual(c.current_balance, Decimal("1500.00"))

    def test_udhaar_dashboard_lists_only_debtors(self):
        debtor = Customer.objects.create(business=self.business, name="Owes")
        record_charge(customer=debtor, amount=Decimal("2500"))
        Customer.objects.create(business=self.business, name="Clear")  # balance 0
        resp = self.client.get(reverse("udhaar"))
        self.assertContains(resp, "Owes")
        self.assertNotContains(resp, ">Clear<")


class CustomerTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a, self.biz_a = make_user_with_business("ia@shop.com", "Iso A")
        self.user_b, self.biz_b = make_user_with_business("ib@shop.com", "Iso B")
        self.cust_b = Customer.objects.create(business=self.biz_b, name="B-Customer")

    def test_cannot_view_other_business_customer(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_business_id"] = self.biz_a.id
        session.save()
        resp = self.client.get(reverse("customers:detail", args=[self.cust_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cannot_post_payment_to_other_business_customer(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_business_id"] = self.biz_a.id
        session.save()
        resp = self.client.post(
            reverse("customers:payment", args=[self.cust_b.pk]), {"amount": "100"}
        )
        self.assertEqual(resp.status_code, 404)
        self.cust_b.refresh_from_db()
        self.assertEqual(self.cust_b.current_balance, Decimal("0.00"))


class EmailReminderTests(TestCase):
    def setUp(self):
        self.user, self.business = make_user_with_business("shop@sharma.com", "Sharma Store")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        self.customer = Customer.objects.create(
            business=self.business, name="Ramesh", email="ramesh@gmail.com",
        )
        record_charge(customer=self.customer, amount=Decimal("2500"))

    def test_send_email_reminder_success(self):
        from django.core import mail
        resp = self.client.post(
            reverse("customers:email_reminder", args=[self.customer.pk]),
            {"email": "ramesh@gmail.com"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["ramesh@gmail.com"])
        self.assertIn("Sharma Store (via Mera Hisaab)", sent.from_email)
        self.assertEqual(sent.reply_to, ["shop@sharma.com"])
        self.assertIn("2500", sent.subject)

    def test_send_email_reminder_no_balance(self):
        c_clear = Customer.objects.create(business=self.business, name="Clean Customer", email="c@test.com")
        resp = self.client.post(
            reverse("customers:email_reminder", args=[c_clear.pk]),
            {"email": "c@test.com"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no pending udhaar")
