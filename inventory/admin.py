from django.contrib import admin

from .models import FoodItem


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "category", "quantity", "unit", "expiry_date")
    list_filter = ("category",)
    search_fields = ("name",)