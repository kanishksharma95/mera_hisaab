from django.contrib import admin

from .models import Product, ProductAttributeValue, ProductCategory


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "business__name")
    autocomplete_fields = ("business",)


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    autocomplete_fields = ("field",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "business", "category", "selling_price", "current_stock", "is_active",
    )
    list_filter = ("is_active", "business")
    search_fields = ("name", "sku", "barcode", "brand", "business__name")
    autocomplete_fields = ("business", "category")
    readonly_fields = ("current_stock",)  # stock only changes via inventory services
    inlines = [ProductAttributeValueInline]
