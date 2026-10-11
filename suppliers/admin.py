from django.contrib import admin

from .models import Supplier, SupplierLedgerEntry


class SupplierLedgerEntryInline(admin.TabularInline):
    model = SupplierLedgerEntry
    extra = 0
    fields = ("created_at", "entry_type", "amount", "balance_after", "description", "method")
    readonly_fields = ("created_at", "balance_after")
    ordering = ("-created_at",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "phone", "current_balance", "is_active")
    list_filter = ("is_active", "business")
    search_fields = ("name", "phone", "email", "gst_number", "business__name")
    autocomplete_fields = ("business",)
    readonly_fields = ("current_balance",)
    inlines = [SupplierLedgerEntryInline]


@admin.register(SupplierLedgerEntry)
class SupplierLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("supplier", "business", "entry_type", "amount", "balance_after", "created_at")
    list_filter = ("entry_type", "business")
    search_fields = ("supplier__name", "business__name", "description", "reference")
    autocomplete_fields = ("business", "supplier", "created_by")
    readonly_fields = ("balance_after",)
    date_hierarchy = "created_at"
