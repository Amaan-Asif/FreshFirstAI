from django.contrib import admin

from .models import FoodItem, FoodLog


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "category", "quantity", "unit", "expiry_date")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(FoodLog)
class FoodLogAdmin(admin.ModelAdmin):
    list_display = ("item_name", "owner", "action", "quantity", "unit", "estimated_cost", "logged_on")
    list_filter = ("action", "reason")
    search_fields = ("item_name",)