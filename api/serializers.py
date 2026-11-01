from django.utils import timezone
from rest_framework import serializers

from inventory.models import FoodItem, FoodLog


class FoodItemSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    status = serializers.CharField(read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = FoodItem
        fields = [
            "id",
            "name",
            "category",
            "category_display",
            "quantity",
            "unit",
            "purchase_date",
            "expiry_date",
            "storage_notes",
            "status",
            "days_until_expiry",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        purchase_date = attrs.get("purchase_date")
        if purchase_date is None:
            purchase_date = (
                self.instance.purchase_date if self.instance else timezone.localdate()
            )
        expiry_date = attrs.get("expiry_date")
        if expiry_date is None and self.instance:
            expiry_date = self.instance.expiry_date

        if expiry_date and expiry_date < purchase_date:
            raise serializers.ValidationError(
                {"expiry_date": "Expiry date cannot be before the purchase date."}
            )
        return attrs


class FoodLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = FoodLog
        fields = [
            "id",
            "item_name",
            "category",
            "category_display",
            "action",
            "action_display",
            "quantity",
            "unit",
            "reason",
            "reason_display",
            "estimated_cost",
            "logged_on",
        ]
        read_only_fields = fields