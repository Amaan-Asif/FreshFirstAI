from django import forms

from .models import FoodItem


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