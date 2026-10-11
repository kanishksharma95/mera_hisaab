from django.contrib import admin

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ("product_name", "quantity", "unit_price", "cost_price",
                       "discount", "tax_percent", "tax_amount", "line_total")
    can_delete = False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "business", "customer", "total", "paid_amount",
                    "due_amount", "payment_status", "created_at")
    list_filter = ("payment_status", "business")
    search_fields = ("invoice_number", "business__name", "customer__name")
    autocomplete_fields = ("business", "customer", "created_by")
    readonly_fields = ("invoice_number", "invoice_seq", "public_token", "subtotal",
                       "discount_total", "order_discount", "tax_total", "total",
                       "paid_amount", "due_amount", "payment_status")
    date_hierarchy = "created_at"
    inlines = [SaleItemInline]
