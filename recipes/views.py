from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from assistant.client import AIServiceError
from assistant.usage import UsageLimitExceeded, check_and_record

from .forms import RecipePreferencesForm
from .services import get_usable_items, suggest_recipes


@login_required
def suggest(request):
    items = get_usable_items(request.user)
    recipes = None
    error = None

    if request.method == "POST":
        form = RecipePreferencesForm(request.POST)
        if form.is_valid() and items:
            try:
                usage = check_and_record(request.user, "recipes")
            except UsageLimitExceeded as exc:
                error = str(exc)
            else:
                try:
                    recipes = suggest_recipes(items, form.cleaned_data)
                except AIServiceError as exc:
                    usage.delete()  # failed requests do not count against the limit
                    error = str(exc)
    else:
        form = RecipePreferencesForm()

    return render(
        request,
        "recipes/suggest.html",
        {
            "form": form,
            "item_count": len(items),
            "recipes": recipes,
            "error": error,
        },
    )