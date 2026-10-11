from django.contrib import admin

from .models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ("product_name", "quantity", "unit_cost", "discount",
                       "tax_percent", "tax_amount", "line_total")
    can_delete = False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("number", "business", "supplier", "total", "paid_amount",
                    "due_amount", "payment_status", "created_at")
    list_filter = ("payment_status", "business")
    search_fields = ("number", "supplier_invoice", "business__name", "supplier__name")
    autocomplete_fields = ("business", "supplier", "created_by")
    readonly_fields = ("number", "number_seq", "subtotal", "discount_total",
                       "order_discount", "tax_total", "total", "paid_amount",
                       "due_amount", "payment_status")
    date_hierarchy = "created_at"
    inlines = [PurchaseItemInline]
