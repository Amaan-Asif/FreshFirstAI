from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import FoodItem, FoodLog


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = [
            "name",
            "category",
            "quantity",
            "unit",
            "purchase_date",
            "expiry_date",
            "storage_notes",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "expiry_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "storage_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Milk"
        self.fields["storage_notes"].widget.attrs["placeholder"] = "e.g. Keep in the fridge door"

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class FoodLogForm(forms.ModelForm):
    class Meta:
        model = FoodLog
        fields = ["action", "quantity", "reason", "estimated_cost", "logged_on"]
        widgets = {
            "logged_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        labels = {
            "logged_on": "Date",
            "reason": "Reason (required if wasted)",
            "estimated_cost": "Estimated cost in ₹ (optional)",
        }

    def __init__(self, *args, item, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        self.fields["estimated_cost"].required = False
        self.fields["quantity"].help_text = (
            f"You have {self._available()} {item.unit} available."
        )

    def _available(self):
        return f"{self.item.quantity.normalize():f}"

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity > self.item.quantity:
            raise forms.ValidationError(
                f"You only have {self._available()} {self.item.unit} of {self.item.name}."
            )
        return quantity

    def clean_estimated_cost(self):
        return self.cleaned_data.get("estimated_cost") or Decimal("0.00")

    def clean_logged_on(self):
        logged_on = self.cleaned_data["logged_on"]
        if logged_on > timezone.localdate():
            raise forms.ValidationError("The date cannot be in the future.")
        return logged_on

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        if action == FoodLog.Action.WASTED and not cleaned.get("reason"):
            self.add_error("reason", "Please choose a reason for the waste.")
        if action == FoodLog.Action.CONSUMED:
            cleaned["reason"] = ""
        return cleaned