from django import forms

DIET_CHOICES = [
    ("any", "No preference"),
    ("vegetarian", "Vegetarian (no meat, fish or eggs)"),
    ("eggetarian", "Eggetarian (vegetarian plus eggs)"),
    ("vegan", "Vegan"),
]

CUISINE_CHOICES = [
    ("any", "Any cuisine"),
    ("Indian", "Indian"),
    ("Italian", "Italian"),
    ("Chinese", "Chinese"),
    ("Mexican", "Mexican"),
    ("Mediterranean", "Mediterranean"),
]

TIME_CHOICES = [
    ("any", "Any time"),
    ("15", "Up to 15 minutes"),
    ("30", "Up to 30 minutes"),
    ("45", "Up to 45 minutes"),
    ("60", "Up to 60 minutes"),
]

COUNT_CHOICES = [(str(number), str(number)) for number in range(1, 6)]


class RecipePreferencesForm(forms.Form):
    diet = forms.ChoiceField(choices=DIET_CHOICES, initial="any")
    cuisine = forms.ChoiceField(choices=CUISINE_CHOICES, initial="any")
    max_time = forms.ChoiceField(
        choices=TIME_CHOICES, initial="any", label="Cooking time"
    )
    count = forms.ChoiceField(
        choices=COUNT_CHOICES, initial="3", label="Number of recipes"
    )
    avoid = forms.CharField(
        required=False,
        max_length=200,
        label="Ingredients to avoid or allergies (optional)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. peanuts, mushrooms"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"

    def clean_avoid(self):
        text = self.cleaned_data.get("avoid", "")
        return text.replace("<", " ").replace(">", " ").strip()