from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from inventory.models import EXPIRING_SOON_DAYS, FoodItem


def home(request):
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    today = timezone.localdate()
    soon_cutoff = today + timedelta(days=EXPIRING_SOON_DAYS)

    items = FoodItem.objects.filter(owner=request.user)

    expired = list(items.filter(expiry_date__lt=today))
    expiring_soon = list(
        items.filter(expiry_date__gte=today, expiry_date__lte=soon_cutoff)
    )
    other = list(items.filter(expiry_date__gt=soon_cutoff))

    sections = [
        {
            "key": "expired",
            "title": "Expired",
            "color": "danger",
            "items": expired,
            "empty": "Nothing has expired. Great job!",
        },
        {
            "key": "soon",
            "title": "Expiring soon",
            "color": "warning",
            "items": expiring_soon,
            "empty": f"Nothing expires in the next {EXPIRING_SOON_DAYS} days.",
        },
        {
            "key": "other",
            "title": "Everything else",
            "color": "success",
            "items": other,
            "empty": "No other items in your inventory.",
        },
    ]

    return render(
        request,
        "core/dashboard.html",
        {
            "sections": sections,
            "total": len(expired) + len(expiring_soon) + len(other),
            "soon_days": EXPIRING_SOON_DAYS,
        },
    )