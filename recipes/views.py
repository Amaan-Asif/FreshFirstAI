from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from assistant.client import AIServiceError
from assistant.usage import UsageLimitExceeded, check_and_record
from planner.models import MealPlanEntry

from .forms import RecipePreferencesForm
from .services import get_usable_items, suggest_recipes


@login_required
def suggest(request):
    items = get_usable_items(request.user)
    recipes = None
    error = None
    showing_previous = False

    if request.method == "POST":
        form = RecipePreferencesForm(request.POST)
        if form.is_valid() and items:
            try:
                usage = check_and_record(request.user, "recipes")
            except UsageLimitExceeded as exc:
                error = str(exc)
            else:
                try:
                    result = suggest_recipes(items, form.cleaned_data)
                except AIServiceError as exc:
                    usage.delete()  # failed requests do not count against the limit
                    error = str(exc)
                else:
                    recipes = [recipe.model_dump() for recipe in result]
                    request.session["suggested_recipes"] = recipes
    else:
        form = RecipePreferencesForm()
        if items:
            recipes = request.session.get("suggested_recipes")
            showing_previous = bool(recipes)

    return render(
        request,
        "recipes/suggest.html",
        {
            "form": form,
            "item_count": len(items),
            "recipes": recipes,
            "error": error,
            "showing_previous": showing_previous,
            "today": timezone.localdate().isoformat(),
            "meal_types": MealPlanEntry.MealType.choices,
        },
    )