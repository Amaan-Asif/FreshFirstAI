import re

from django.utils import timezone

from inventory.models import FoodItem
from planner.models import MealPlanEntry


def _normalise(name):
    """Lower-case a food name, drop brackets, and make simple plurals singular."""
    text = re.sub(r"\(.*?\)", " ", str(name)).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    words = []
    for word in text.split():
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("oes") and len(word) > 4:
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def _have(needed, available):
    """True if the needed ingredient matches anything in `available`.

    Both are normalised names. "garlic" matches "garlic paste" and vice versa.
    """
    needed_words = set(needed.split())
    for have in available:
        have_words = set(have.split())
        if not have_words or not needed_words:
            continue
        if have_words <= needed_words or needed_words <= have_words:
            return True
    return False


def build_shopping_list(user, start, end):
    """Work out what to buy for the planned meals between `start` and `end`.

    Returns (items, meal_count). Meals before today are skipped. Each item is a
    dict with "name", "meals" (titles of the meals that need it) and "note".
    """
    today = timezone.localdate()
    first_day = max(start, today)

    entries = list(
        MealPlanEntry.objects.filter(
            owner=user, date__range=(first_day, end)
        ).order_by("date", "id")
    )

    stock = [
        (_normalise(item.name), item.expiry_date)
        for item in FoodItem.objects.filter(owner=user, expiry_date__gte=today)
    ]
    stock_names = [name for name, _expiry in stock]

    needed = {}
    for entry in entries:
        # Only stock that has not expired by the day of the meal counts.
        available = [name for name, expiry in stock if expiry >= entry.date]

        names = list(entry.extra_ingredients) + list(entry.inventory_ingredients)
        for raw in names:
            name = str(raw).strip()
            key = _normalise(name)
            if not key or _have(key, available):
                continue

            item = needed.setdefault(
                key,
                {"name": name[:1].upper() + name[1:], "meals": [], "note": ""},
            )
            if entry.title not in item["meals"]:
                item["meals"].append(entry.title)
            if _have(key, stock_names):
                item["note"] = "Your current stock will expire before this meal."

    items = sorted(needed.values(), key=lambda item: item["name"].lower())
    return items, len(entries)