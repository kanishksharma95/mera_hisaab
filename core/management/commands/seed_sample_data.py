"""
Seed realistic sample organization data for Mera Hisaab.

Creates a complete, production-grade Indian retail setup:
- Store: Sharma Supermarket & General Store (Jaipur, Rajasthan)
- Demo accounts: demo@merahisaab.app and kanishksharma5078@gmail.com
- Real FMCG products with Indian barcodes and margins
- Real regular customers with Udhaar (Khata) balances
- Real wholesale suppliers with payables
- Real shop expenses (Rent, Electricity, Chai, Salary, Transport)
- Real sales transactions with cash, UPI, and credit billing
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from businesses.models import Business, BusinessMembership, BusinessType
from customers.models import Customer
from customers.services import record_charge
from expenses.models import ExpenseCategory
from expenses.services import ensure_default_categories, record_expense
from payments.models import PaymentMethod
from payments.services import ensure_default_methods
from products.models import ProductCategory, Product
from sales.services import create_sale
from suppliers.models import Supplier
from suppliers.services import record_bill

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds realistic organization data for testing and demonstrations."

    def handle(self, *args, **options):
        self.stdout.write("Starting sample data seeding for Sharma Supermarket...")

        with transaction.atomic():
            # 1. Users
            demo_user, _ = User.objects.get_or_create(
                email="demo@merahisaab.app",
                defaults={"full_name": "Demo Admin", "is_staff": True, "is_superuser": True},
            )
            demo_user.set_password("MeraHisaab@2026")
            demo_user.save()

            kanishk_user, _ = User.objects.get_or_create(
                email="kanishksharma5078@gmail.com",
                defaults={"full_name": "Kanishak Sharma", "is_staff": True, "is_superuser": True},
            )
            kanishk_user.set_password("MeraHisaab@2026")
            kanishk_user.save()

            # 2. Business Type
            btype, _ = BusinessType.objects.get_or_create(
                name="Grocery / Supermarket",
                defaults={"description": "Retail FMCG, Kirana and Grocery Store", "icon": "🛒"},
            )

            # 3. Business (Tenant)
            business, created = Business.objects.get_or_create(
                name="Sharma Supermarket & General Store",
                defaults={
                    "business_type": btype,
                    "owner_name": "Kanishak Sharma",
                    "phone": "9876543210",
                    "email": "kanishksharma5078@gmail.com",
                    "city": "Jaipur",
                    "state": "Rajasthan",
                    "address": "Shop 14, Main Market, Malviya Nagar",
                    "pincode": "302017",
                    "gst_number": "08AABCS1429B1Z8",
                    "invoice_prefix": "SGS-",
                    "currency": "INR",
                },
            )

            # 4. Link Memberships
            BusinessMembership.objects.get_or_create(
                user=demo_user, business=business,
                defaults={"role": BusinessMembership.Role.OWNER},
            )
            BusinessMembership.objects.get_or_create(
                user=kanishk_user, business=business,
                defaults={"role": BusinessMembership.Role.OWNER},
            )

            # 5. Methods & Categories
            ensure_default_methods(business)
            ensure_default_categories(business)

            cash_m = PaymentMethod.objects.for_business(business).get(code="cash")
            upi_m = PaymentMethod.objects.for_business(business).get(code="upi")
            credit_m = PaymentMethod.objects.for_business(business).get(code="credit")

            # 6. Product Categories
            cat_grains, _ = ProductCategory.objects.get_or_create(business=business, name="Atta, Rice & Grains")
            cat_oils, _ = ProductCategory.objects.get_or_create(business=business, name="Edible Oils & Ghee")
            cat_dairy, _ = ProductCategory.objects.get_or_create(business=business, name="Dairy & Breakfast")
            cat_snacks, _ = ProductCategory.objects.get_or_create(business=business, name="Snacks & Beverages")
            cat_cleaning, _ = ProductCategory.objects.get_or_create(business=business, name="Household & Personal Care")

            # 7. Products
                # Grains & Sugar
                ("Madhur Pure Sugar 1kg", cat_grains, "8901234567890", "42.00", "48.00", "0", "50", "kg"),
                ("India Gate Basmati Rice 5kg", cat_grains, "8901234567891", "420.00", "490.00", "0", "20", "pack"),
                ("Aashirvaad Shudh Chakki Atta 10kg", cat_grains, "8901725181222", "410.00", "460.00", "0", "45", "bag"),
                ("India Gate Basmati Rice Feast 5kg", cat_grains, "8901507000213", "380.00", "445.00", "0", "30", "bag"),
                ("Tata Sampann Toor Dal 1kg", cat_grains, "8904043902341", "145.00", "175.00", "0", "50", "kg"),
                # Oils & Ghee
                ("Fortune Sunlite Refined Sunflower Oil 1L", cat_oils, "8906007280014", "125.00", "148.00", "5", "60", "bottle"),
                ("Amul Pure Ghee 1L Tin", cat_oils, "8901262010888", "560.00", "640.00", "12", "25", "tin"),
                ("Tata Salt Vacuum Evaporated 1kg", cat_oils, "8904043901005", "23.50", "28.00", "0", "120", "pkt"),
                # Dairy
                ("Amul Butter 500g", cat_dairy, "8901262010055", "255.00", "285.00", "12", "20", "pack"),
                ("Amul Taaza Homogenised Toned Milk 1L", cat_dairy, "8901262010123", "64.00", "74.00", "0", "40", "pack"),
                # Snacks & Beverages
                ("Tata Tea Premium 250g", cat_snacks, "8901234567892", "110.00", "135.00", "5", "30", "pack"),
                ("Nescafe Classic Coffee 50g", cat_snacks, "8901234567899", "100.00", "110.00", "0", "15", "jar"),
                ("Maggi 2-Minute Masala Noodles 70g", cat_snacks, "8901058852331", "11.50", "14.00", "12", "150", "pack"),
                ("Parle-G Gold Glucose Biscuits 1kg", cat_snacks, "8901719101014", "110.00", "130.00", "18", "35", "pack"),
                ("Brooke Bond Red Label Tea 500g", cat_snacks, "8901030012214", "260.00", "315.00", "5", "40", "box"),
                ("Coca Cola 750ml PET", cat_snacks, "8901764012234", "36.00", "45.00", "28", "48", "bottle"),
                ("Haldiram's Nagpur Bhujia 400g", cat_snacks, "8904063201452", "98.00", "120.00", "12", "55", "pack"),
                # Personal Care & Cleaning
                ("Dettol Original Bath Soap 125g (Pack of 3)", cat_cleaning, "8901396001223", "125.00", "155.00", "18", "30", "pack"),
                ("Surf Excel Quick Wash Detergent 1kg", cat_cleaning, "8901030789221", "175.00", "215.00", "18", "40", "kg"),
                ("Colgate MaxFresh Red Gel 150g", cat_cleaning, "8901314010214", "88.00", "110.00", "18", "60", "tube"),
            ]

            created_prods = {}
            for name, cat, barcode, cost, sell, tax, stock, unit in products_data:
                prod, _ = Product.objects.get_or_create(
                    business=business, barcode=barcode,
                    defaults={
                        "name": name,
                        "category": cat,
                        "purchase_price": Decimal(cost),
                        "selling_price": Decimal(sell),
                        "tax_percent": Decimal(tax),
                        "current_stock": Decimal(stock),
                        "unit": unit,
                    },
                )
                created_prods[name] = prod

            # 8. Customers with Udhaar Balances
            cust_ramesh, _ = Customer.objects.get_or_create(
                business=business, name="Ramesh Verma",
                defaults={"phone": "9811223344", "address": "Quarter 12, Malviya Nagar"}
            )
            if cust_ramesh.current_balance == Decimal("0"):
                record_charge(customer=cust_ramesh, amount=Decimal("3200.00"), description="Pichla Udhaar (Bahi-Khata)")

            cust_sunita, _ = Customer.objects.get_or_create(
                business=business, name="Sunita Sharma",
                defaults={"phone": "9822334455", "address": "B-44, Model Town"}
            )
            if cust_sunita.current_balance == Decimal("0"):
                record_charge(customer=cust_sunita, amount=Decimal("1450.00"), description="Pichla Udhaar (Purani Diary)")

            cust_vikram, _ = Customer.objects.get_or_create(
                business=business, name="Vikram Singh",
                defaults={"phone": "9833445566", "address": "Plot 8, Jagatpura"}
            )
            if cust_vikram.current_balance == Decimal("0"):
                record_charge(customer=cust_vikram, amount=Decimal("850.00"), description="Pichla Udhaar")

            cust_pooja, _ = Customer.objects.get_or_create(
                business=business, name="Pooja Gupta",
                defaults={"phone": "9844556677", "address": "C-12, Malviya Nagar"}
            )

            # 9. Suppliers
            supp_mittal, _ = Supplier.objects.get_or_create(
                business=business, name="Mittal Wholesale FMCG Agency",
                defaults={"phone": "9829011223", "address": "Shop 4, Muhana Mandi"}
            )
            if supp_mittal.current_balance == Decimal("0"):
                record_bill(supplier=supp_mittal, amount=Decimal("18500.00"), description="Pichla Purana Baki")

            supp_dairy, _ = Supplier.objects.get_or_create(
                business=business, name="Rajasthan Dairy & Amul Agency",
                defaults={"phone": "9829022334", "address": "Sanganer Road"}
            )
            if supp_dairy.current_balance == Decimal("0"):
                record_bill(supplier=supp_dairy, amount=Decimal("6200.00"), description="Milk & Ghee Supply Bill")

            # 10. Expenses
            cats = {c.name: c for c in ExpenseCategory.objects.for_business(business)}
            today = timezone.localdate()

            expenses_to_add = [
                ("Rent", "15000.00", today - timedelta(days=10), "Monthly Shop Rent (Malviya Nagar)"),
                ("Electricity", "2850.00", today - timedelta(days=5), "Electricity Bill (Bijli)"),
                ("Salaries", "12000.00", today - timedelta(days=8), "Staff helper salary (Sonu & Rohit)"),
                ("Transport", "750.00", today - timedelta(days=2), "Tempo goods carriage from Mandi"),
                ("Tea & Snacks", "420.00", today, "Customer & staff daily chai-nashta"),
                ("Packaging", "580.00", today - timedelta(days=3), "Bio carry bags & packing tape"),
            ]

            for cat_name, amt, spent_date, note in expenses_to_add:
                cat_obj = cats.get(cat_name)
                if cat_obj and not cat_obj.expenses.filter(note=note).exists():
                    record_expense(
                        business=business,
                        category=cat_obj,
                        amount=Decimal(amt),
                        method=cash_m,
                        spent_on=spent_date,
                        note=note,
                        user=demo_user,
                    )

            # 11. Sales (Historical & Today's billing)
            p_atta = created_prods["Aashirvaad Shudh Chakki Atta 10kg"]
            p_oil = created_prods["Fortune Sunlite Refined Sunflower Oil 1L"]
            p_butter = created_prods["Amul Butter 500g"]
            p_maggi = created_prods["Maggi 2-Minute Masala Noodles 70g"]
            p_tea = created_prods["Brooke Bond Red Label Tea 500g"]
            p_rice = created_prods["India Gate Basmati Rice Feast 5kg"]

            # Only seed demo sales if less than 3 sales exist
            from sales.models import Sale
            if Sale.objects.for_business(business).count() < 3:
                # Sale 1: Cash sale
                create_sale(
                    business=business, user=demo_user, customer=cust_pooja,
                    items=[
                        {"product": p_atta, "quantity": 1},
                        {"product": p_oil, "quantity": 2},
                        {"product": p_maggi, "quantity": 5},
                    ],
                    payments=[{"method": cash_m, "amount": Decimal("5000.00")}],
                    notes="Counter Cash sale (PAID)",
                )

                # Sale 2: UPI / QR payment sale
                create_sale(
                    business=business, user=demo_user, customer=cust_sunita,
                    items=[
                        {"product": p_rice, "quantity": 1},
                        {"product": p_tea, "quantity": 1},
                        {"product": p_butter, "quantity": 1},
                    ],
                    payments=[{"method": upi_m, "amount": Decimal("5000.00")}],
                    notes="Paid via PhonePe QR (PAID)",
                )

                # Sale 3: Udhaar sale to Ramesh Verma
                create_sale(
                    business=business, user=demo_user, customer=cust_ramesh,
                    items=[
                        {"product": p_atta, "quantity": 1},
                        {"product": p_oil, "quantity": 1},
                    ],
                    payments=[],  # 100% Credit / Udhaar
                    notes="Udhaar khata mein likha",
                )

        self.stdout.write(self.style.SUCCESS("Successfully seeded sample data for Sharma Supermarket!"))
