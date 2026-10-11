from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from businesses.models import Business, BusinessMembership, BusinessType, BusinessTypeField
from inventory.models import InventoryTransaction
from inventory.services import adjust_stock, record_transaction

from .models import Product, ProductAttributeValue, ProductCategory

User = get_user_model()


def make_user_with_business(email, business_name, business_type=None):
    user = User.objects.create_user(email=email, password="pw!23456X", full_name="Owner")
    business = Business.objects.create(name=business_name, business_type=business_type)
    BusinessMembership.objects.create(
        user=user, business=business, role=BusinessMembership.Role.OWNER
    )
    return user, business


class ProductCreationTests(TestCase):
    def setUp(self):
        self.mobile = BusinessType.objects.get(name="Mobile")
        self.user, self.business = make_user_with_business(
            "a@shop.com", "A Store", self.mobile
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_create_product_records_opening_stock(self):
        resp = self.client.post(
            reverse("products:add"),
            {
                "name": "iPhone 15",
                "sku": "IP15",
                "purchase_price": "60000",
                "selling_price": "72000",
                "tax_percent": "18",
                "unit": "pcs",
                "min_stock_level": "2",
                "opening_stock": "5",
                # dynamic Mobile attributes (Brand, Model, IMEI required)
                **self._attr_payload({"Brand": "Apple", "Model": "15", "IMEI": "123456"}),
            },
        )
        product = Product.objects.get(name="iPhone 15")
        self.assertRedirects(resp, reverse("products:detail", args=[product.pk]))
        self.assertEqual(product.business, self.business)
        self.assertEqual(product.current_stock, Decimal("5"))
        # An opening-stock inventory transaction must exist and match.
        txn = InventoryTransaction.objects.get(product=product)
        self.assertEqual(txn.kind, InventoryTransaction.Kind.OPENING)
        self.assertEqual(txn.quantity, Decimal("5"))
        self.assertEqual(txn.balance_after, Decimal("5"))

    def test_dynamic_attributes_saved(self):
        self.client.post(
            reverse("products:add"),
            {
                "name": "Galaxy S24", "purchase_price": "50000", "selling_price": "60000",
                "tax_percent": "18", "unit": "pcs", "min_stock_level": "1", "opening_stock": "0",
                **self._attr_payload({"Brand": "Samsung", "Model": "S24", "IMEI": "999"}),
            },
        )
        product = Product.objects.get(name="Galaxy S24")
        values = {av.field.name: av.value for av in product.attributes.all()}
        self.assertEqual(values["Brand"], "Samsung")
        self.assertEqual(values["IMEI"], "999")

    def test_required_dynamic_attribute_enforced(self):
        resp = self.client.post(
            reverse("products:add"),
            {
                "name": "No IMEI Phone", "purchase_price": "1", "selling_price": "2",
                "tax_percent": "0", "unit": "pcs", "min_stock_level": "0", "opening_stock": "0",
                # IMEI (required) omitted
                **self._attr_payload({"Brand": "X", "Model": "Y"}),
            },
        )
        self.assertEqual(resp.status_code, 200)  # form re-rendered with errors
        self.assertFalse(Product.objects.filter(name="No IMEI Phone").exists())

    def _attr_payload(self, mapping):
        payload = {}
        for f in BusinessTypeField.objects.filter(business_type=self.mobile):
            if f.name in mapping:
                payload[f"attr_{f.id}"] = mapping[f.name]
        return payload


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.user, self.business = make_user_with_business("b@shop.com", "B Store")
        self.product = Product.objects.create(
            business=self.business, name="Rice", unit="kg",
            purchase_price=40, selling_price=55, current_stock=0, min_stock_level=Decimal("10"),
        )

    def test_record_transaction_updates_stock_and_balance(self):
        record_transaction(product=self.product, kind="purchase", quantity=Decimal("25.5"))
        record_transaction(product=self.product, kind="sale", quantity=Decimal("-5.5"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("20.000"))
        last = InventoryTransaction.objects.filter(product=self.product).first()
        self.assertEqual(last.balance_after, Decimal("20.000"))

    def test_adjust_stock_sets_absolute_quantity(self):
        record_transaction(product=self.product, kind="opening", quantity=Decimal("30"))
        txn = adjust_stock(product=self.product, new_quantity=Decimal("12"), note="count")
        self.assertEqual(txn.quantity, Decimal("-18.000"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("12.000"))

    def test_adjust_stock_no_change_returns_none(self):
        record_transaction(product=self.product, kind="opening", quantity=Decimal("10"))
        self.assertIsNone(adjust_stock(product=self.product, new_quantity=Decimal("10")))

    def test_low_stock_property(self):
        record_transaction(product=self.product, kind="opening", quantity=Decimal("10"))
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_low_stock)  # 10 <= min 10
        record_transaction(product=self.product, kind="purchase", quantity=Decimal("5"))
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_low_stock)


class ProductTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a, self.biz_a = make_user_with_business("ta@shop.com", "Tenant A")
        self.user_b, self.biz_b = make_user_with_business("tb@shop.com", "Tenant B")
        self.prod_b = Product.objects.create(
            business=self.biz_b, name="B-Secret Product", selling_price=100
        )

    def test_user_cannot_view_other_business_product(self):
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_business_id"] = self.biz_a.id
        session.save()
        resp = self.client.get(reverse("products:detail", args=[self.prod_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_product_list_only_shows_own_products(self):
        Product.objects.create(business=self.biz_a, name="A-Product", selling_price=10)
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_business_id"] = self.biz_a.id
        session.save()
        resp = self.client.get(reverse("products:list"))
        self.assertContains(resp, "A-Product")
        self.assertNotContains(resp, "B-Secret Product")

    def test_for_business_manager_scopes_products(self):
        self.assertFalse(
            Product.objects.for_business(self.biz_a).filter(name="B-Secret Product").exists()
        )
        self.assertTrue(
            Product.objects.for_business(self.biz_b).filter(name="B-Secret Product").exists()
        )


class CategoryTests(TestCase):
    def setUp(self):
        self.user, self.business = make_user_with_business("c@shop.com", "C Store")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_create_category_scoped_to_business(self):
        self.client.post(reverse("products:category_add"), {"name": "Snacks", "description": ""})
        cat = ProductCategory.objects.get(name="Snacks")
        self.assertEqual(cat.business, self.business)
