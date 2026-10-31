from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import MealEntryForm
from .models import MealPlanEntry

# Breakfast first, then lunch, dinner, snack
MEAL_ORDER = {
    key: position for position, (key, _label) in enumerate(MealPlanEntry.MealType.choices)
}


def _monday_of(day):
    return day - timedelta(days=day.weekday())


def _week_url(day):
    return f"{reverse('planner:week')}?start={day.isoformat()}"


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