from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assistant.models import AIUsage
from inventory.models import FoodItem, FoodLog
from planner.models import MealPlanEntry

DEMO_USERNAME = "demo"
DEFAULT_PASSWORD = "FreshFirst-Demo-2026"

# name, category, quantity, unit, days until expiry, storage notes
INVENTORY = [
    ("Old Bread", "grains", "1", "pack", -2, "Check for mould before eating"),
    ("Curd", "dairy", "1", "pack", -1, ""),
    ("Tomatoes", "vegetables", "4", "pcs", 1, "Use in a curry"),
    ("Spinach", "vegetables", "1", "pack", 2, "Keep in the fridge"),
    ("Paneer", "dairy", "1", "pack", 3, ""),
    ("Milk", "dairy", "1.5", "l", 3, "Fridge door"),
    ("Bananas", "fruits", "6", "pcs", 5, ""),
    ("Yogurt", "dairy", "2", "pack", 9, ""),
    ("Apples", "fruits", "6", "pcs", 12, ""),
    ("Onions", "vegetables", "1.5", "kg", 14, "Store in a cool, dark place"),
    ("Frozen Peas", "frozen", "1", "pack", 60, "Freezer"),
    ("Toor Dal", "pulses", "2", "kg", 150, ""),
    ("Basmati Rice", "grains", "5", "kg", 180, "Airtight container"),
]

# days ago, name, category, unit, quantity, action, reason, cost in rupees
LOGS = [
    (1, "Milk", "dairy", "l", "0.5", "consumed", "", "0"),
    (2, "Bread", "grains", "pack", "1", "wasted", "expired", "25"),
    (3, "Spinach", "vegetables", "pack", "1", "wasted", "spoiled", "30"),
    (4, "Rice", "grains", "kg", "0.5", "consumed", "", "0"),
    (5, "Yogurt", "dairy", "pack", "1", "wasted", "too_much", "45"),
    (6, "Tomatoes", "vegetables", "pcs", "3", "consumed", "", "0"),
    (7, "Lettuce", "vegetables", "pcs", "1", "wasted", "expired", "30"),
    (8, "Bananas", "fruits", "pcs", "4", "wasted", "spoiled", "40"),
    (9, "Toor Dal", "pulses", "kg", "0.25", "consumed", "", "0"),
    (10, "Paneer", "dairy", "pack", "1", "consumed", "", "0"),
    (11, "Curd", "dairy", "pack", "1", "wasted", "expired", "35"),
    (13, "Bread", "grains", "pack", "1", "wasted", "expired", "25"),
    (14, "Leftover curry", "other", "pack", "1", "wasted", "leftovers", "60"),
    (15, "Milk", "dairy", "l", "1", "wasted", "spoiled", "60"),
    (17, "Apples", "fruits", "pcs", "2", "consumed", "", "0"),
    (18, "Cauliflower", "vegetables", "pcs", "1", "wasted", "spoiled", "40"),
    (20, "Rice", "grains", "kg", "1", "wasted", "too_much", "70"),
    (22, "Onions", "vegetables", "kg", "0.5", "consumed", "", "0"),
    (24, "Bread", "grains", "pack", "1", "wasted", "expired", "25"),
    (26, "Yogurt", "dairy", "pack", "1", "consumed", "", "0"),
    (28, "Bananas", "fruits", "pcs", "3", "wasted", "disliked", "30"),
]

# day offset from today, meal, title, description, minutes, servings,
# ingredients from the inventory, ingredients to buy, steps
MEALS = [
    (
        -1, "dinner", "Dal Tadka",
        "A simple, comforting dal with a spiced tempering.",
        30, 3,
        ["Toor Dal", "Onions"],
        ["Garlic", "Cumin seeds"],
        [
            "Pressure cook the toor dal with turmeric and salt until soft.",
            "Heat oil, then add cumin seeds, chopped garlic and onions.",
            "Pour the tempering into the dal and simmer for five minutes.",
            "Serve hot with rice.",
        ],
    ),
    (
        0, "breakfast", "Vegetable Poha",
        "A light, quick breakfast with onions and tomatoes.",
        20, 2,
        ["Onions", "Tomatoes"],
        ["Poha", "Peanuts", "Curry leaves", "Lemon"],
        [
            "Rinse the poha and let it soften for five minutes.",
            "Saute onions and tomatoes with curry leaves in a pan.",
            "Add the poha, peanuts and salt and toss gently.",
            "Finish with a squeeze of lemon juice.",
        ],
    ),
    (
        0, "dinner", "Palak Paneer",
        "A classic curry that uses up your spinach and paneer.",
        30, 2,
        ["Spinach", "Paneer", "Onions"],
        ["Garlic", "Ginger", "Garam masala"],
        [
            "Blanch the spinach for two minutes and blend it into a smooth puree.",
            "Cube the paneer and lightly fry it until golden.",
            "Saute onions, garlic and ginger with garam masala until fragrant.",
            "Add the spinach puree and simmer for five minutes.",
            "Stir in the paneer and serve hot.",
        ],
    ),
    (
        1, "lunch", "Tomato Dal",
        "A comforting dal made with tomatoes and toor dal.",
        35, 3,
        ["Toor Dal", "Tomatoes", "Onions"],
        ["Cumin seeds", "Coriander leaves"],
        [
            "Cook the toor dal until soft and mash it lightly.",
            "Fry cumin seeds, then onions and chopped tomatoes until they soften.",
            "Add the dal with water and simmer for ten minutes.",
            "Garnish with coriander leaves.",
        ],
    ),
    (
        2, "dinner", "Vegetable Pulao",
        "Fragrant rice with peas and onions.",
        35, 3,
        ["Basmati Rice", "Frozen Peas", "Onions"],
        ["Whole spices", "Cashews"],
        [
            "Rinse the basmati rice and soak it for twenty minutes.",
            "Fry the whole spices and onions in oil until golden.",
            "Add the rice, peas, cashews, water and salt.",
            "Cover and cook until the rice is fluffy.",
        ],
    ),
    (
        3, "dinner", "Paneer Bhurji",
        "A quick scramble of paneer with onions and tomatoes.",
        20, 2,
        ["Paneer", "Onions", "Tomatoes"],
        ["Green chillies", "Turmeric powder"],
        [
            "Crumble the paneer into small pieces.",
            "Saute onions, green chillies and tomatoes with turmeric powder.",
            "Add the paneer and cook for three minutes.",
            "Serve with warm flatbread.",
        ],
    ),
]


class Command(BaseCommand):
    help = "Create (or reset) the public demo account with realistic sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password for the demo account (default: %(default)s)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        User = get_user_model()

        user, _created = User.objects.get_or_create(
            username=DEMO_USERNAME, defaults={"email": "demo@example.com"}
        )
        user.set_password(options["password"])
        user.is_staff = False
        user.is_superuser = False
        user.save()

        # Start fresh: remove only the demo account's own data.
        FoodItem.objects.filter(owner=user).delete()
        FoodLog.objects.filter(owner=user).delete()
        MealPlanEntry.objects.filter(owner=user).delete()
        AIUsage.objects.filter(user=user).delete()

        for name, category, quantity, unit, days, notes in INVENTORY:
            FoodItem.objects.create(
                owner=user,
                name=name,
                category=category,
                quantity=Decimal(quantity),
                unit=unit,
                purchase_date=today - timedelta(days=3),
                expiry_date=today + timedelta(days=days),
                storage_notes=notes,
            )

        for days_ago, name, category, unit, quantity, action, reason, cost in LOGS:
            FoodLog.objects.create(
                owner=user,
                item_name=name,
                category=category,
                unit=unit,
                action=action,
                quantity=Decimal(quantity),
                reason=reason,
                estimated_cost=Decimal(cost),
                logged_on=today - timedelta(days=days_ago),
            )

        for offset, meal, title, text, minutes, servings, have, buy, steps in MEALS:
            MealPlanEntry.objects.create(
                owner=user,
                date=today + timedelta(days=offset),
                meal_type=meal,
                title=title,
                description=text,
                cooking_time_minutes=minutes,
                servings=servings,
                inventory_ingredients=have,
                extra_ingredients=buy,
                steps=steps,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo account ready (username '{DEMO_USERNAME}'): "
                f"{len(INVENTORY)} food items, {len(LOGS)} history records, "
                f"{len(MEALS)} planned meals."
            )
        )