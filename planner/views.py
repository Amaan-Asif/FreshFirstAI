from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import MealEntryForm, RecipeAddForm
from .models import MealPlanEntry

# Breakfast first, then lunch, dinner, snack
MEAL_ORDER = {
    key: position for position, (key, _label) in enumerate(MealPlanEntry.MealType.choices)
}


def _monday_of(day):
    return day - timedelta(days=day.weekday())


def _week_url(day):
    return f"{reverse('planner:week')}?start={day.isoformat()}"


def _clean_text_list(values, max_items, max_length):
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values[:max_items]:
        text = str(value).strip()[:max_length]
        if text:
            cleaned.append(text)
    return cleaned


def _clean_number(value, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


@login_required
def week(request):
    today = timezone.localdate()

    try:
        anchor = date.fromisoformat(request.GET.get("start", ""))
    except ValueError:
        anchor = today
    if abs((anchor - today).days) > 365:
        anchor = today

    monday = _monday_of(anchor)
    sunday = monday + timedelta(days=6)

    entries = MealPlanEntry.objects.filter(
        owner=request.user, date__range=(monday, sunday)
    )

    by_day = {monday + timedelta(days=offset): [] for offset in range(7)}
    for entry in entries:
        by_day[entry.date].append(entry)

    days = []
    for day, day_entries in by_day.items():
        day_entries.sort(key=lambda item: (MEAL_ORDER[item.meal_type], item.id))
        days.append({"date": day, "is_today": day == today, "entries": day_entries})

    return render(
        request,
        "planner/week.html",
        {
            "days": days,
            "monday": monday,
            "sunday": sunday,
            "prev_start": (monday - timedelta(days=7)).isoformat(),
            "next_start": (monday + timedelta(days=7)).isoformat(),
            "is_current_week": monday == _monday_of(today),
        },
    )


@login_required
def entry_create(request):
    if request.method == "POST":
        form = MealEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.owner = request.user
            entry.save()
            messages.success(request, f"{entry.title} was added to your meal plan.")
            return redirect(_week_url(entry.date))
    else:
        try:
            initial_date = date.fromisoformat(request.GET.get("date", ""))
        except ValueError:
            initial_date = timezone.localdate()
        form = MealEntryForm(initial={"date": initial_date})

    return render(request, "planner/entry_form.html", {"form": form})


@login_required
def entry_detail(request, pk):
    entry = get_object_or_404(MealPlanEntry, pk=pk, owner=request.user)
    return render(request, "planner/entry_detail.html", {"entry": entry})


@login_required
@require_POST
def entry_delete(request, pk):
    entry = get_object_or_404(MealPlanEntry, pk=pk, owner=request.user)
    day = entry.date
    title = entry.title
    entry.delete()
    messages.success(request, f"{title} was removed from your meal plan.")
    return redirect(_week_url(day))


@login_required
@require_POST
def recipe_add(request):
    """Add one of the last AI recipe suggestions (kept in the session) to the plan."""
    form = RecipeAddForm(request.POST)
    if not form.is_valid():
        problems = "; ".join(
            error for errors in form.errors.values() for error in errors
        )
        messages.error(request, f"Could not add the recipe: {problems}")
        return redirect("recipes:suggest")

    suggestions = request.session.get("suggested_recipes", [])
    index = form.cleaned_data["index"]
    if index >= len(suggestions):
        messages.error(
            request,
            "That recipe suggestion is no longer available. "
            "Please generate new suggestions.",
        )
        return redirect("recipes:suggest")

    recipe = suggestions[index]
    entry = MealPlanEntry.objects.create(
        owner=request.user,
        date=form.cleaned_data["date"],
        meal_type=form.cleaned_data["meal_type"],
        title=(str(recipe.get("title", "")).strip()[:200] or "Recipe"),
        description=str(recipe.get("description", "")).strip()[:1000],
        cooking_time_minutes=_clean_number(recipe.get("cooking_time_minutes"), 1, 1000),
        servings=_clean_number(recipe.get("servings"), 1, 100),
        inventory_ingredients=_clean_text_list(recipe.get("inventory_ingredients"), 40, 100),
        extra_ingredients=_clean_text_list(recipe.get("extra_ingredients"), 40, 100),
        steps=_clean_text_list(recipe.get("steps"), 30, 1000),
    )

    messages.success(
        request,
        f"{entry.title} was added to your meal plan for {entry.date:%A, %d %b}.",
    )
    return redirect("recipes:suggest")