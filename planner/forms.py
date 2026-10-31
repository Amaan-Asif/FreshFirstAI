from django import forms
from django.utils import timezone

from .models import MealPlanEntry


def validate_plan_date(day):
    if abs((day - timezone.localdate()).days) > 365:
        raise forms.ValidationError("Please choose a date within a year of today.")
    return day


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
        return validate_plan_date(self.cleaned_data["date"])


class RecipeAddForm(forms.Form):
    """Checks the 'Add to meal plan' button on a recipe suggestion."""

    index = forms.IntegerField(min_value=0, max_value=20)
    date = forms.DateField()
    meal_type = forms.ChoiceField(choices=MealPlanEntry.MealType.choices)

    def clean_date(self):
        return validate_plan_date(self.cleaned_data["date"])