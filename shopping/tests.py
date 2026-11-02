from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from inventory.models import FoodItem
from planner.models import MealPlanEntry

from .services import _have, _normalise, build_shopping_list

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)
WEEK_START = date(2026, 10, 26)
WEEK_END = date(2026, 11, 1)


def add_stock(owner, name, days_to_expiry=10):
    return FoodItem.objects.create(
        owner=owner,
        name=name,
        category=FoodItem.Category.OTHER,
        quantity=Decimal("1.00"),
        unit=FoodItem.Unit.PIECES,
        purchase_date=FIXED_TODAY - timedelta(days=3),
        expiry_date=FIXED_TODAY + timedelta(days=days_to_expiry),
    )


def add_meal(owner, title, day=FIXED_TODAY, extra=(), inventory=()):
    return MealPlanEntry.objects.create(
        owner=owner,
        date=day,
        meal_type="dinner",
        title=title,
        extra_ingredients=list(extra),
        inventory_ingredients=list(inventory),
    )


def names(items):
    return [item["name"] for item in items]


class NormaliseTests(SimpleTestCase):
    def test_plurals_are_made_singular(self):
        examples = {
            "Onions": "onion",
            "Tomatoes": "tomato",
            "Potatoes": "potato",
            "Berries": "berry",
            "Lentils": "lentil",
            "Chickpeas": "chickpea",
            "Glass": "glass",
            "Rice": "rice",
        }
        for original, expected in examples.items():
            with self.subTest(name=original):
                self.assertEqual(_normalise(original), expected)

    def test_brackets_and_punctuation_are_removed(self):
        self.assertEqual(_normalise("Garlic (fresh)"), "garlic")
        self.assertEqual(_normalise("Lemon-juice!"), "lemon juice")


class HaveTests(SimpleTestCase):
    def test_exact_match(self):
        self.assertTrue(_have("onion", ["onion", "rice"]))

    def test_partial_match_works_in_both_directions(self):
        self.assertTrue(_have("garlic", ["garlic paste"]))
        self.assertTrue(_have("garlic paste", ["garlic"]))

    def test_no_match(self):
        self.assertFalse(_have("ginger", ["garlic"]))
        self.assertFalse(_have("onion", []))


class ShoppingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)


class BuildListTests(ShoppingTestCase):
    def build(self, user=None, start=WEEK_START, end=WEEK_END):
        return build_shopping_list(user or self.alice, start, end)

    def test_no_planned_meals_gives_an_empty_list(self):
        items, meal_count = self.build()
        self.assertEqual(items, [])
        self.assertEqual(meal_count, 0)

    def test_missing_ingredients_are_listed_in_alphabetical_order(self):
        add_meal(self.alice, "Dal", extra=["Onion", "Garlic"])
        items, meal_count = self.build()
        self.assertEqual(names(items), ["Garlic", "Onion"])
        self.assertEqual(items[0]["meals"], ["Dal"])
        self.assertEqual(meal_count, 1)

    def test_ingredients_already_in_stock_are_skipped(self):
        add_stock(self.alice, "Onion")
        add_meal(self.alice, "Dal", extra=["Onion", "Garlic"])
        items, _ = self.build()
        self.assertEqual(names(items), ["Garlic"])

    def test_plurals_and_capitals_still_match_the_stock(self):
        add_stock(self.alice, "Tomato")
        add_meal(self.alice, "Salad", extra=["TOMATOES"])
        items, _ = self.build()
        self.assertEqual(items, [])

    def test_stock_that_expires_before_the_meal_is_listed_with_a_note(self):
        add_stock(self.alice, "Spinach", days_to_expiry=1)
        add_meal(
            self.alice, "Salad", day=FIXED_TODAY + timedelta(days=3),
            inventory=["Spinach"],
        )
        items, _ = self.build(start=FIXED_TODAY, end=FIXED_TODAY + timedelta(days=6))
        self.assertEqual(names(items), ["Spinach"])
        self.assertEqual(
            items[0]["note"], "Your current stock will expire before this meal."
        )

    def test_already_expired_stock_does_not_count(self):
        add_stock(self.alice, "Onion", days_to_expiry=-1)
        add_meal(self.alice, "Dal", extra=["Onion"])
        items, _ = self.build()
        self.assertEqual(names(items), ["Onion"])
        self.assertEqual(items[0]["note"], "")

    def test_meals_before_today_are_skipped(self):
        add_meal(self.alice, "Old Dal", day=date(2026, 10, 30), extra=["Garlic"])
        items, meal_count = self.build()
        self.assertEqual(items, [])
        self.assertEqual(meal_count, 0)

    def test_the_same_ingredient_is_merged_across_meals(self):
        add_meal(self.alice, "Dal", extra=["Onion"])
        add_meal(
            self.alice, "Curry", day=FIXED_TODAY + timedelta(days=1),
            extra=["onions"],
        )
        items, meal_count = self.build(
            start=FIXED_TODAY, end=FIXED_TODAY + timedelta(days=6)
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["meals"], ["Dal", "Curry"])
        self.assertEqual(meal_count, 2)

    def test_other_users_meals_and_stock_are_ignored(self):
        add_stock(self.bob, "Garlic")
        add_meal(self.bob, "Bob Curry", extra=["Ginger"])
        add_meal(self.alice, "Dal", extra=["Garlic"])
        items, meal_count = self.build()
        self.assertEqual(names(items), ["Garlic"])
        self.assertEqual(meal_count, 1)

    def test_inventory_ingredients_are_checked_too(self):
        add_meal(self.alice, "Rice Bowl", inventory=["Rice"])
        items, _ = self.build()
        self.assertEqual(names(items), ["Rice"])

    def test_item_names_start_with_a_capital_letter(self):
        add_meal(self.alice, "Salad", extra=["lemon juice"])
        items, _ = self.build()
        self.assertEqual(names(items), ["Lemon juice"])


class ShoppingViewTests(ShoppingTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)
        self.url = reverse("shopping:list")

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_no_planned_meals_shows_a_friendly_message(self):
        response = self.client.get(self.url)
        self.assertContains(response, "No planned meals to shop for in this week.")

    def test_page_lists_the_items_to_buy(self):
        add_meal(self.alice, "Salad", extra=["Lemon juice"])
        response = self.client.get(self.url)
        self.assertContains(response, "Lemon juice")
        self.assertContains(response, "For: Salad")
        self.assertEqual(response.context["meal_count"], 1)
        self.assertEqual(len(response.context["items"]), 1)

    def test_everything_in_stock_shows_a_success_message(self):
        add_stock(self.alice, "Lemon juice")
        add_meal(self.alice, "Salad", extra=["Lemon juice"])
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "You already have everything you need for your 1 planned meal(s) this week.",
        )

    def test_another_week_can_be_viewed(self):
        add_meal(self.alice, "Today Salad", extra=["Lemon juice"])
        response = self.client.get(self.url, {"start": "2026-11-02"})
        self.assertEqual(response.context["monday"], date(2026, 11, 2))
        self.assertFalse(response.context["is_current_week"])
        self.assertContains(response, "No planned meals to shop for in this week.")
        self.assertNotContains(response, "Lemon juice")

    def test_page_never_shows_another_users_data(self):
        add_meal(self.bob, "Bob Curry", extra=["Secret Saffron"])
        response = self.client.get(self.url)
        self.assertNotContains(response, "Secret Saffron")
        self.assertNotContains(response, "Bob Curry")