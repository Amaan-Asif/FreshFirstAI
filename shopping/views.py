from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .services import build_shopping_list


@login_required
def shopping_list(request):
    today = timezone.localdate()

    try:
        anchor = date.fromisoformat(request.GET.get("start", ""))
    except ValueError:
        anchor = today
    if abs((anchor - today).days) > 365:
        anchor = today

    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)

    items, meal_count = build_shopping_list(request.user, monday, sunday)

    return render(
        request,
        "shopping/list.html",
        {
            "items": items,
            "meal_count": meal_count,
            "monday": monday,
            "sunday": sunday,
            "prev_start": (monday - timedelta(days=7)).isoformat(),
            "next_start": (monday + timedelta(days=7)).isoformat(),
            "is_current_week": monday == today - timedelta(days=today.weekday()),
        },
    )