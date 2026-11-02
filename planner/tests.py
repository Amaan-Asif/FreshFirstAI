from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import MealPlanEntry

User = get_user_model()

# Every test pretends that today is this date (a Sunday), so results never change.
FIXED_TODAY = date(2026, 11, 1)


def make_entry(owner, day=FIXED_TODAY, meal_type="dinner", title="Dal and rice", **extra):
    return MealPlanEntry.objects.create(
        owner=owner, date=day, meal_type=meal_type, title=title, **extra
    )


def week_url(day_text):
    return f"{reverse('planner:week')}?start={day_text}"


class PlannerTestCase(TestCase):
    """Creates two users, fixes today's date, and logs in as alice."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.login(username="alice", password="pass12345")


class AccessTests(PlannerTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        entry = make_entry(self.alice)
        self.client.logout()
        urls = [
            reverse("planner:week"),
            reverse("planner:add"),
            reverse("planner:add_recipe"),
            reverse("planner:detail", args=[entry.pk]),
            reverse("planner:delete", args=[entry.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('accounts:login')}?next={url}"
                )


class WeekViewTests(PlannerTestCase):
    def test_week_has_seven_days_from_monday_to_sunday(self):
        response = self.client.get(reverse("planner:week"))
        days = response.context["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["date"], date(2026, 10, 26))
        self.assertEqual(days[0]["date"].strftime("%A"), "Monday")
        self.assertEqual(days[-1]["date"], date(2026, 11, 1))

    def test_only_today_is_marked(self):
        response = self.client.get(reverse("planner:week"))
        flags = [day["is_today"] for day in response.context["days"]]
        self.assertEqual(flags, [False] * 6 + [True])

    def test_week_shows_only_own_meals(self):
        make_entry(self.alice, title="Alice Dal")
        make_entry(self.bob, title="Bob Curry")
        response = self.client.get(reverse("planner:week"))
        self.assertContains(response, "Alice Dal")
        self.assertNotContains(response, "Bob Curry")

    def test_meals_are_ordered_from_breakfast_to_snack(self):
        make_entry(self.alice, meal_type="snack", title="Fruit Snack")
        make_entry(self.alice, meal_type="dinner", title="Dinner Dal")
        make_entry(self.alice, meal_type="breakfast", title="Poha")
        make_entry(self.alice, meal_type="lunch", title="Lunch Thali")
        response = self.client.get(reverse("planner:week"))
        titles = [entry.title for entry in response.context["days"][-1]["entries"]]
        self.assertEqual(titles, ["Poha", "Lunch Thali", "Dinner Dal", "Fruit Snack"])

    def test_start_parameter_shows_another_week(self):
        response = self.client.get(reverse("planner:week"), {"start": "2026-11-10"})
        self.assertEqual(response.context["monday"], date(2026, 11, 9))
        self.assertEqual(response.context["sunday"], date(2026, 11, 15))
        self.assertFalse(response.context["is_current_week"])

    def test_invalid_or_far_away_start_falls_back_to_this_week(self):
        for bad_value in ("garbage", "2030-01-01"):
            with self.subTest(start=bad_value):
                response = self.client.get(reverse("planner:week"), {"start": bad_value})
                self.assertEqual(response.context["monday"], date(2026, 10, 26))
                self.assertTrue(response.context["is_current_week"])

    def test_previous_and_next_links_move_by_one_week(self):
        response = self.client.get(reverse("planner:week"))
        self.assertEqual(response.context["prev_start"], "2026-10-19")
        self.assertEqual(response.context["next_start"], "2026-11-02")

    def test_meal_from_another_week_is_not_shown(self):
        make_entry(self.alice, day=date(2026, 11, 3), title="Next Week Soup")
        response = self.client.get(reverse("planner:week"))
        self.assertNotContains(response, "Next Week Soup")


class CreateTests(PlannerTestCase):
    def test_add_page_prefills_the_date_from_the_link(self):
        response = self.client.get(reverse("planner:add"), {"date": "2026-11-03"})
        self.assertEqual(response.context["form"].initial["date"], date(2026, 11, 3))

    def test_create_sets_owner_and_returns_to_that_week(self):
        data = {
            "date": "2026-11-03",
            "meal_type": "lunch",
            "title": "Dal and rice",
            "notes": "",
        }
        response = self.client.post(reverse("planner:add"), data)
        self.assertRedirects(response, week_url("2026-11-03"))
        entry = MealPlanEntry.objects.get()
        self.assertEqual(entry.owner, self.alice)
        self.assertEqual(entry.meal_type, "lunch")

    def test_date_more_than_a_year_away_is_rejected(self):
        data = {"date": "2028-01-01", "meal_type": "dinner", "title": "Far Away", "notes": ""}
        response = self.client.post(reverse("planner:add"), data)
        self.assertContains(response, "Please choose a date within a year of today.")
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_title_is_required(self):
        data = {"date": "2026-11-03", "meal_type": "dinner", "title": "", "notes": ""}
        response = self.client.post(reverse("planner:add"), data)
        self.assertIn("title", response.context["form"].errors)
        self.assertFalse(MealPlanEntry.objects.exists())


class DetailAndDeleteTests(PlannerTestCase):
    def test_detail_shows_own_meal(self):
        entry = make_entry(self.alice, title="Alice Dal")
        response = self.client.get(reverse("planner:detail", args=[entry.pk]))
        self.assertContains(response, "Alice Dal")

    def test_cannot_view_another_users_meal(self):
        entry = make_entry(self.bob, title="Bob Curry")
        response = self.client.get(reverse("planner:detail", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_by_get_request_is_not_allowed(self):
        entry = make_entry(self.alice)
        response = self.client.get(reverse("planner:delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(MealPlanEntry.objects.filter(pk=entry.pk).exists())

    def test_user_can_delete_own_meal(self):
        entry = make_entry(self.alice, day=date(2026, 11, 3))
        response = self.client.post(reverse("planner:delete", args=[entry.pk]))
        self.assertRedirects(response, week_url("2026-11-03"))
        self.assertFalse(MealPlanEntry.objects.filter(pk=entry.pk).exists())

    def test_cannot_delete_another_users_meal(self):
        entry = make_entry(self.bob)
        response = self.client.post(reverse("planner:delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MealPlanEntry.objects.filter(pk=entry.pk).exists())


class RecipeAddTests(PlannerTestCase):
    RECIPE = {
        "title": "Palak Paneer",
        "description": "A classic curry.",
        "cooking_time_minutes": 30,
        "servings": 2,
        "inventory_ingredients": ["Spinach", "Paneer"],
        "extra_ingredients": ["Onion"],
        "steps": ["Blanch the spinach.", "Blend it smooth."],
    }

    def save_suggestions(self, suggestions):
        session = self.client.session
        session["suggested_recipes"] = suggestions
        session.save()

    def post(self, **overrides):
        data = {"index": "0", "date": "2026-11-02", "meal_type": "dinner"}
        data.update(overrides)
        return self.client.post(reverse("planner:add_recipe"), data)

    def test_recipe_is_added_with_all_its_details(self):
        self.save_suggestions([self.RECIPE])
        response = self.post()
        self.assertRedirects(
            response, reverse("recipes:suggest"), fetch_redirect_response=False
        )
        entry = MealPlanEntry.objects.get()
        self.assertEqual(entry.owner, self.alice)
        self.assertEqual(entry.date, date(2026, 11, 2))
        self.assertEqual(entry.meal_type, "dinner")
        self.assertEqual(entry.title, "Palak Paneer")
        self.assertEqual(entry.description, "A classic curry.")
        self.assertEqual(entry.cooking_time_minutes, 30)
        self.assertEqual(entry.servings, 2)
        self.assertEqual(entry.inventory_ingredients, ["Spinach", "Paneer"])
        self.assertEqual(entry.extra_ingredients, ["Onion"])
        self.assertEqual(entry.steps, ["Blanch the spinach.", "Blend it smooth."])

    def test_bad_numbers_and_lists_are_cleaned(self):
        messy = {
            "title": "   ",
            "cooking_time_minutes": "abc",
            "servings": 5000,
            "inventory_ingredients": ["  Rice  ", ""],
            "extra_ingredients": [],
            "steps": "not a list",
        }
        self.save_suggestions([messy])
        self.post()
        entry = MealPlanEntry.objects.get()
        self.assertEqual(entry.title, "Recipe")
        self.assertIsNone(entry.cooking_time_minutes)
        self.assertIsNone(entry.servings)
        self.assertEqual(entry.inventory_ingredients, ["Rice"])
        self.assertEqual(entry.steps, [])

    def test_unknown_recipe_number_is_refused(self):
        self.save_suggestions([self.RECIPE])
        response = self.post(index="5")
        self.assertRedirects(
            response, reverse("recipes:suggest"), fetch_redirect_response=False
        )
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_invalid_meal_type_is_refused(self):
        self.save_suggestions([self.RECIPE])
        response = self.client.post(
            reverse("planner:add_recipe"),
            {"index": "0", "date": "2026-11-02", "meal_type": "brunch"},
            follow=True,
        )
        self.assertContains(response, "Could not add the recipe")
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_date_more_than_a_year_away_is_refused(self):
        self.save_suggestions([self.RECIPE])
        response = self.client.post(
            reverse("planner:add_recipe"),
            {"index": "0", "date": "2028-01-01", "meal_type": "dinner"},
            follow=True,
        )
        self.assertContains(response, "Please choose a date within a year of today.")
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_get_request_is_not_allowed(self):
        response = self.client.get(reverse("planner:add_recipe"))
        self.assertEqual(response.status_code, 405)

    def test_without_saved_suggestions_nothing_is_added(self):
        response = self.client.post(
            reverse("planner:add_recipe"),
            {"index": "0", "date": "2026-11-02", "meal_type": "dinner"},
            follow=True,
        )
        self.assertContains(response, "no longer available")
        self.assertFalse(MealPlanEntry.objects.exists())