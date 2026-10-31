from django import forms
from django.utils import timezone

from .models import MealPlanEntry


class MealEntryForm(forms.ModelForm):
    class Meta:
        model = MealPlanEntry
        fields = ["date", "meal_type", "title", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "date": "Date",
            "meal_type": "Meal",
            "title": "What are you eating?",
            "notes": "Notes (optional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        self.fields["title"].widget.attrs["placeholder"] = "e.g. Dal and rice"

    def clean_date(self):
        day = self.cleaned_data["date"]
        if abs((day - timezone.localdate()).days) > 365:
            raise forms.ValidationError("Please choose a date within a year of today.")
        return day