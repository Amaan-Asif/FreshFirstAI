from collections import Counter
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from analytics.services import build_analytics
from assistant.models import AIUsage
from inventory.models import FoodItem, FoodLog
from planner.models import MealPlanEntry
from shopping.services import build_shopping_list

User = get_user_model()

# A Monday, so the meal plan week starts today.
FIXED_TODAY = date(2026, 11, 2)
DEFAULT_PASSWORD = "FreshFirst-Demo-2026"


class SeedDemoTests(TestCase):
    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def seed(self, **options):
        call_command("seed_demo", stdout=StringIO(), **options)
        return User.objects.get(username="demo")

    def test_creates_a_regular_user_that_can_log_in(self):
        user = self.seed()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(self.client.login(username="demo", password=DEFAULT_PASSWORD))

    def test_password_option_is_used(self):
        self.seed(password="Another-Pass-123")
        self.assertTrue(self.client.login(username="demo", password="Another-Pass-123"))
        self.client.logout()
        self.assertFalse(self.client.login(username="demo", password=DEFAULT_PASSWORD))

    def test_inventory_has_items_in_every_status(self):
        user = self.seed()
        items = FoodItem.objects.filter(owner=user)
        statuses = Counter(item.status for item in items)
        self.assertEqual(statuses, {"expired": 2, "expiring_soon": 4, "fresh": 7})

    def test_no_item_expires_before_it_was_bought(self):
        user = self.seed()
        for item in FoodItem.objects.filter(owner=user):
            with self.subTest(item=item.name):
                item.full_clean()  # raises an error if something is invalid

    def test_waste_statistics(self):
        user = self.seed()
        stats = build_analytics(user)["stats"]
        self.assertEqual(stats["total_count"], 21)
        self.assertEqual(stats["wasted_count"], 13)
        self.assertEqual(stats["consumed_count"], 8)
        self.assertEqual(stats["waste_rate"], 61.9)
        self.assertEqual(stats["total_wasted_cost"], 515.0)
        self.assertEqual(stats["top_item_name"], "Bread")
        self.assertEqual(stats["top_item_cost"], 75.0)
        self.assertEqual(stats["top_reason"], "Expired before use")
        self.assertEqual(stats["top_reason_count"], 5)

    def test_charts_are_filled_in(self):
        user = self.seed()
        charts = build_analytics(user)["charts"]
        self.assertEqual(charts["category"]["labels"][0], "Grains and bread")
        self.assertEqual(charts["category"]["values"][0], 145.0)
        self.assertGreaterEqual(len(charts["category"]["labels"]), 4)
        self.assertGreaterEqual(len(charts["reason"]["labels"]), 4)
        self.assertEqual(len(charts["trend"]["labels"]), 30)
        # every record falls inside the 30-day window, so nothing is left out
        self.assertEqual(sum(charts["trend"]["values"]), 515.0)

    def test_meal_plan_has_complete_recipes(self):
        user = self.seed()
        entries = MealPlanEntry.objects.filter(owner=user)
        self.assertEqual(entries.count(), 6)
        self.assertEqual(entries.filter(date=FIXED_TODAY).count(), 2)
        for entry in entries:
            with self.subTest(meal=entry.title):
                self.assertTrue(entry.description)
                self.assertTrue(entry.cooking_time_minutes)
                self.assertTrue(entry.servings)
                self.assertTrue(entry.inventory_ingredients)
                self.assertTrue(entry.extra_ingredients)
                self.assertGreaterEqual(len(entry.steps), 4)

    def test_shopping_list_has_items_to_buy(self):
        user = self.seed()
        items, meal_count = build_shopping_list(
            user, FIXED_TODAY, FIXED_TODAY + timedelta(days=6)
        )
        names = [item["name"] for item in items]

        self.assertEqual(meal_count, 5)  # yesterday's dinner is skipped
        for expected in ("Garlic", "Ginger", "Cashews", "Lemon"):
            self.assertIn(expected, names)
        for in_stock in ("Paneer", "Onions", "Basmati Rice", "Toor Dal"):
            self.assertNotIn(in_stock, names)

        # Tomatoes are in stock but expire before the Paneer Bhurji dinner.
        tomatoes = next(item for item in items if item["name"] == "Tomatoes")
        self.assertEqual(
            tomatoes["note"], "Your current stock will expire before this meal."
        )

    def test_running_twice_resets_instead_of_duplicating(self):
        self.seed()
        user = self.seed()
        self.assertEqual(User.objects.filter(username="demo").count(), 1)
        self.assertEqual(FoodItem.objects.filter(owner=user).count(), 13)
        self.assertEqual(FoodLog.objects.filter(owner=user).count(), 21)
        self.assertEqual(MealPlanEntry.objects.filter(owner=user).count(), 6)

    def test_other_users_data_is_untouched(self):
        alice = User.objects.create_user("alice", password="pass12345")
        FoodItem.objects.create(
            owner=alice,
            name="Alice Cheese",
            category="dairy",
            quantity=1,
            unit="pack",
            purchase_date=FIXED_TODAY,
            expiry_date=FIXED_TODAY + timedelta(days=5),
        )
        self.seed()
        self.seed()
        self.assertEqual(FoodItem.objects.filter(owner=alice).count(), 1)
        self.assertEqual(FoodItem.objects.count(), 14)

    def test_ai_usage_of_the_demo_account_is_cleared(self):
        user = self.seed()
        AIUsage.objects.create(user=user, feature="recipes")
        self.seed()
        self.assertEqual(AIUsage.objects.filter(user=user).count(), 0)

    def test_main_pages_load_for_the_demo_user(self):
        self.seed()
        self.client.login(username="demo", password=DEFAULT_PASSWORD)
        pages = [
            "core:dashboard",
            "inventory:list",
            "inventory:history",
            "analytics:dashboard",
            "planner:week",
            "shopping:list",
            "recipes:suggest",
        ]
        for name in pages:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        analytics_page = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(analytics_page, "₹515.00")