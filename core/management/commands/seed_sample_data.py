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
            # Seed suppliers and purchases for any Kiryana or related store in the system
            for other_b in Business.objects.all():
                # Ensure default payment methods & categories exist
                ensure_default_methods(other_b)
                ensure_default_categories(other_b)
                pm_c = PaymentMethod.objects.for_business(other_b).filter(code="cash").first()
                pm_u = PaymentMethod.objects.for_business(other_b).filter(code="upi").first()

                # Add 3 diverse Wholesale Suppliers
                s_balaji, _ = Supplier.objects.get_or_create(
                    business=other_b, name="Balaji Wholesale Agency",
                    defaults={"phone": "9829011223", "address": "Shop 12, Krishi Mandi", "gst_number": "08AAAAA1234B1Z2"}
                )
                s_dairy, _ = Supplier.objects.get_or_create(
                    business=other_b, name="Amul & Rajasthan Dairy Depot",
                    defaults={"phone": "9829044556", "address": "Dairy Road, Sanganer"}
                )
                s_spices, _ = Supplier.objects.get_or_create(
                    business=other_b, name="Kisan Masala & Dryfruits Traders",
                    defaults={"phone": "9829077889", "address": "Godown 4, Grain Market"}
                )

                # Categories & Products
                cat_gen, _ = ProductCategory.objects.get_or_create(business=other_b, name="General Grocery")
                cat_bev, _ = ProductCategory.objects.get_or_create(business=other_b, name="Tea & Beverages")

                p_sug, _ = Product.objects.get_or_create(
                    business=other_b, name="Madhur Sugar 1kg",
                    defaults={"category": cat_gen, "purchase_price": Decimal("42.00"), "selling_price": Decimal("48.00"), "current_stock": Decimal("100"), "min_stock_level": Decimal("20"), "unit": "kg"}
                )
                p_ric, _ = Product.objects.get_or_create(
                    business=other_b, name="Basmati Rice 5kg",
                    defaults={"category": cat_gen, "purchase_price": Decimal("420.00"), "selling_price": Decimal("490.00"), "current_stock": Decimal("50"), "min_stock_level": Decimal("10"), "unit": "pack"}
                )
                p_tea_k, _ = Product.objects.get_or_create(
                    business=other_b, name="Tata Tea Gold 250g",
                    defaults={"category": cat_bev, "purchase_price": Decimal("115.00"), "selling_price": Decimal("140.00"), "current_stock": Decimal("40"), "min_stock_level": Decimal("10"), "unit": "pack"}
                )
                p_ghee_k, _ = Product.objects.get_or_create(
                    business=other_b, name="Amul Pure Ghee 1L",
                    defaults={"category": cat_gen, "purchase_price": Decimal("560.00"), "selling_price": Decimal("640.00"), "current_stock": Decimal("30"), "min_stock_level": Decimal("5"), "unit": "tin"}
                )

                # Seed Purchases if less than 3 exist for this business
                from purchases.models import Purchase as PModel
                from purchases.services import create_purchase as do_create_purchase
                if PModel.objects.for_business(other_b).count() < 3:
                    u_creator = other_b.memberships.first().user if other_b.memberships.exists() else kanishk_user
                    
                    # 1. Grain & Sugar restock - Partial Payment (Supplier Udhaar)
                    do_create_purchase(
                        business=other_b, user=u_creator, supplier=s_balaji,
                        supplier_invoice="INV-BALAJI-441", notes="Weekly staple restock (Partial Credit)",
                        items=[
                            {"product": p_sug, "quantity": Decimal("40.000"), "unit_cost": Decimal("42.00")},
                            {"product": p_ric, "quantity": Decimal("15.000"), "unit_cost": Decimal("420.00")},
                        ],
                        payments=[{"method": pm_c, "amount": Decimal("4000.00")}] if pm_c else [],
                    )

                    # 2. Dairy & Ghee batch - Paid in Full via UPI
                    do_create_purchase(
                        business=other_b, user=u_creator, supplier=s_dairy,
                        supplier_invoice="BILL-AMUL-992", notes="Fresh Ghee & Dairy batch (Paid Full via UPI)",
                        items=[
                            {"product": p_ghee_k, "quantity": Decimal("15.000"), "unit_cost": Decimal("560.00")},
                        ],
                        payments=[{"method": pm_u, "amount": Decimal("8400.00")}] if pm_u else [],
                    )

                    # 3. Premium Tea & Masala - 100% Credit (Payable later)
                    do_create_purchase(
                        business=other_b, user=u_creator, supplier=s_spices,
                        supplier_invoice="INV-KISAN-310", notes="Tea supply on 15 days credit bill",
                        items=[
                            {"product": p_tea_k, "quantity": Decimal("25.000"), "unit_cost": Decimal("115.00")},
                        ],
                        payments=[],  # 100% Udhaar
                    )

                # Seed expenses for this business
                from expenses.models import Expense as EModel
                from expenses.services import record_expense as do_record_expense
                if EModel.objects.for_business(other_b).count() < 3:
                    u_creator = other_b.memberships.first().user if other_b.memberships.exists() else kanishk_user
                    cats_k = {c.name: c for c in ExpenseCategory.objects.for_business(other_b)}
                    today_k = timezone.localdate()
                    if "Rent" in cats_k and pm_u:
                        do_record_expense(business=other_b, category=cats_k["Rent"], amount=Decimal("12000.00"), method=pm_u, spent_on=today_k - timedelta(days=5), note="Monthly Shop Rent paid via UPI", user=u_creator)
                    if "Electricity" in cats_k and pm_u:
                        do_record_expense(business=other_b, category=cats_k["Electricity"], amount=Decimal("2450.00"), method=pm_u, spent_on=today_k - timedelta(days=3), note="Electricity bill (Bijli ka bill)", user=u_creator)
                    if "Tea & Snacks" in cats_k and pm_c:
                        do_record_expense(business=other_b, category=cats_k["Tea & Snacks"], amount=Decimal("150.00"), method=pm_c, spent_on=today_k, note="Daily Chai nashta for staff & customer", user=u_creator)
                    if "Transport" in cats_k and pm_c:
                        do_record_expense(business=other_b, category=cats_k["Transport"], amount=Decimal("600.00"), method=pm_c, spent_on=today_k - timedelta(days=1), note="Tempo carriage from Mandi", user=u_creator)
                    if "Packaging" in cats_k and pm_c:
                        do_record_expense(business=other_b, category=cats_k["Packaging"], amount=Decimal("450.00"), method=pm_c, spent_on=today_k - timedelta(days=2), note="Carry bags and packing tape roll", user=u_creator)



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

            # 7. Products (with realistic min stock levels for low-stock alerts)
            products_data = [
                # Grains & Sugar (name, cat, barcode, cost, sell, tax, stock, unit, min_stock)
                ("Madhur Pure Sugar 1kg", cat_grains, "8901234567890", "42.00", "48.00", "0", "50", "kg", "10"),
                ("India Gate Basmati Rice 5kg", cat_grains, "8901234567891", "420.00", "490.00", "0", "20", "pack", "5"),
                ("Aashirvaad Shudh Chakki Atta 10kg", cat_grains, "8901725181222", "410.00", "460.00", "0", "45", "bag", "10"),
                ("India Gate Basmati Rice Feast 5kg", cat_grains, "8901507000213", "380.00", "445.00", "0", "29", "bag", "30"),
                ("Tata Sampann Toor Dal 1kg", cat_grains, "8904043902341", "145.00", "175.00", "0", "50", "kg", "10"),
                # Oils & Ghee
                ("Fortune Sunlite Refined Sunflower Oil 1L", cat_oils, "8906007280014", "125.00", "148.00", "5", "60", "bottle", "15"),
                ("Amul Pure Ghee 1L Tin", cat_oils, "8901262010888", "560.00", "640.00", "12", "25", "tin", "5"),
                ("Tata Salt Vacuum Evaporated 1kg", cat_oils, "8904043901005", "23.50", "28.00", "0", "120", "pkt", "25"),
                # Dairy
                ("Amul Butter 500g", cat_dairy, "8901262010055", "255.00", "285.00", "12", "19", "pack", "20"),
                ("Amul Taaza Homogenised Toned Milk 1L", cat_dairy, "8901262010123", "64.00", "74.00", "0", "40", "pack", "15"),
                # Snacks & Beverages
                ("Tata Tea Premium 250g", cat_snacks, "8901234567892", "110.00", "135.00", "5", "30", "pack", "10"),
                ("Nescafe Classic Coffee 50g", cat_snacks, "8901234567899", "100.00", "110.00", "0", "15", "jar", "5"),
                ("Maggi 2-Minute Masala Noodles 70g", cat_snacks, "8901058852331", "11.50", "14.00", "12", "150", "pack", "30"),
                ("Parle-G Gold Glucose Biscuits 1kg", cat_snacks, "8901719101014", "110.00", "130.00", "18", "35", "pack", "10"),
                ("Brooke Bond Red Label Tea 500g", cat_snacks, "8901030012214", "260.00", "315.00", "5", "40", "box", "10"),
                ("Coca Cola 750ml PET", cat_snacks, "8901764012234", "36.00", "45.00", "28", "48", "bottle", "12"),
                ("Haldiram's Nagpur Bhujia 400g", cat_snacks, "8904063201452", "98.00", "120.00", "12", "55", "pack", "15"),
                # Personal Care & Cleaning
                ("Dettol Original Bath Soap 125g (Pack of 3)", cat_cleaning, "8901396001223", "125.00", "155.00", "18", "30", "pack", "10"),
                ("Surf Excel Quick Wash Detergent 1kg", cat_cleaning, "8901030789221", "175.00", "215.00", "18", "40", "kg", "10"),
                ("Colgate MaxFresh Red Gel 150g", cat_cleaning, "8901314010214", "88.00", "110.00", "18", "60", "tube", "15"),
            ]

            created_prods = {}
            for name, cat, barcode, cost, sell, tax, stock, unit, min_s in products_data:
                prod, _ = Product.objects.update_or_create(
                    business=business, barcode=barcode,
                    defaults={
                        "name": name,
                        "category": cat,
                        "purchase_price": Decimal(cost),
                        "selling_price": Decimal(sell),
                        "tax_percent": Decimal(tax),
                        "current_stock": Decimal(stock),
                        "min_stock_level": Decimal(min_s),
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

            # 12. Purchases (Stock-In from Wholesalers)
            from purchases.models import Purchase
            from purchases.services import create_purchase
            if Purchase.objects.for_business(business).count() < 2:
                # Purchase 1: Balaji / Mittal Wholesale (Partial Credit)
                p_sugar = created_prods.get("Madhur Pure Sugar 1kg", p_atta)
                create_purchase(
                    business=business,
                    user=demo_user,
                    supplier=supp_mittal,
                    supplier_invoice="INV-MITTAL-782",
                    notes="Sugar and Atta restock shipment (Partially Paid)",
                    items=[
                        {"product": p_sugar, "quantity": Decimal("25.000"), "unit_cost": Decimal("42.00")},
                        {"product": p_atta, "quantity": Decimal("10.000"), "unit_cost": Decimal("410.00")},
                    ],
                    payments=[{"method": cash_m, "amount": Decimal("3150.00")}],
                )

                # Purchase 2: Dairy Supply via UPI (Full Paid)
                create_purchase(
                    business=business,
                    user=demo_user,
                    supplier=supp_dairy,
                    supplier_invoice="BILL-AMUL-409",
                    notes="Milk and Ghee restock via UPI (PAID)",
                    items=[
                        {"product": p_butter, "quantity": Decimal("20.000"), "unit_cost": Decimal("255.00")},
                    ],
                    payments=[{"method": upi_m, "amount": Decimal("5100.00")}],
                )

        self.stdout.write(self.style.SUCCESS("Successfully seeded sample data for Sharma Supermarket!"))

