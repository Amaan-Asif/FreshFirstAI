from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from assistant.client import AIServiceError
from assistant.models import AIUsage
from inventory.models import FoodItem

from .forms import RecipePreferencesForm
from .services import (
    Recipe,
    RecipeSuggestions,
    _clean_ingredient_lists,
    build_prompt,
    get_usable_items,
    suggest_recipes,
)

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)


def make_item(owner, name="Milk", days_to_expiry=10, **overrides):
    values = {
        "owner": owner,
        "name": name,
        "category": FoodItem.Category.OTHER,
        "quantity": Decimal("2.00"),
        "unit": FoodItem.Unit.LITRES,
        "purchase_date": FIXED_TODAY - timedelta(days=3),
        "expiry_date": FIXED_TODAY + timedelta(days=days_to_expiry),
    }
    values.update(overrides)
    return FoodItem.objects.create(**values)


def make_recipe(**overrides):
    values = {
        "title": "Palak Paneer",
        "description": "A classic curry.",
        "cooking_time_minutes": 30,
        "servings": 2,
        "inventory_ingredients": ["Spinach"],
        "extra_ingredients": ["Onion"],
        "steps": ["Blanch the spinach.", "Blend it smooth."],
    }
    values.update(overrides)
    return Recipe(**values)


def preferences(**overrides):
    data = {
        "diet": "any",
        "cuisine": "any",
        "max_time": "any",
        "count": "3",
        "avoid": "",
    }
    data.update(overrides)
    return data


class FixedDateTestCase(TestCase):
    """Creates two users and pretends that today is FIXED_TODAY."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)


class UsableItemsTests(FixedDateTestCase):
    def test_excludes_expired_items_and_other_users_items(self):
        make_item(self.alice, "Fresh", 5)
        make_item(self.alice, "Stale", -1)
        make_item(self.bob, "Bob Item", 5)
        names = [item.name for item in get_usable_items(self.alice)]
        self.assertEqual(names, ["Fresh"])

    def test_item_expiring_today_is_still_usable(self):
        make_item(self.alice, "Today", 0)
        names = [item.name for item in get_usable_items(self.alice)]
        self.assertEqual(names, ["Today"])

    def test_items_are_sorted_by_expiry_then_name(self):
        make_item(self.alice, "Zucchini", 2)
        make_item(self.alice, "Apple", 2)
        make_item(self.alice, "Mango", 1)
        names = [item.name for item in get_usable_items(self.alice)]
        self.assertEqual(names, ["Mango", "Apple", "Zucchini"])


class BuildPromptTests(FixedDateTestCase):
    def test_lists_each_ingredient_with_quantity_and_expiry(self):
        make_item(self.alice, "Spinach", 0, quantity=Decimal("1.00"), unit="pack")
        make_item(self.alice, "Paneer", 3, quantity=Decimal("250.00"), unit="g")
        items = get_usable_items(self.alice)
        prompt = build_prompt(items, preferences(), 3)

        self.assertIn("- Spinach: 1 pack (expires today)", prompt)
        self.assertIn("- Paneer: 250 g (expires in 3 day(s))", prompt)
        self.assertLess(prompt.index("Spinach:"), prompt.index("Paneer:"))

    def test_quantities_are_written_as_plain_numbers(self):
        make_item(self.alice, "Rice", 10, quantity=Decimal("10.00"), unit="kg")
        make_item(self.alice, "Milk", 10, quantity=Decimal("0.50"), unit="l")
        prompt = build_prompt(get_usable_items(self.alice), preferences(), 3)

        self.assertIn("- Rice: 10 kg", prompt)
        self.assertIn("- Milk: 0.5 l", prompt)
        self.assertNotIn("E+", prompt)

    def test_default_preferences_wording(self):
        make_item(self.alice, "Spinach", 2)
        prompt = build_prompt(get_usable_items(self.alice), preferences(), 3)

        self.assertIn("Suggest 3 different recipes", prompt)
        self.assertIn("no dietary restriction", prompt)
        self.assertIn("any cuisine", prompt)
        self.assertIn("no time limit", prompt)
        self.assertIn("<avoid>nothing</avoid>", prompt)

    def test_chosen_preferences_wording(self):
        make_item(self.alice, "Spinach", 2)
        chosen = preferences(
            diet="vegan", cuisine="Indian", max_time="30", avoid="peanuts, mushrooms"
        )
        prompt = build_prompt(get_usable_items(self.alice), chosen, 2)

        self.assertIn("Suggest 2 different recipes", prompt)
        self.assertIn("vegan (no animal products at all)", prompt)
        self.assertIn("Indian cuisine", prompt)
        self.assertIn("at most 30 minutes", prompt)
        self.assertIn("<avoid>peanuts, mushrooms</avoid>", prompt)


class CleanIngredientTests(SimpleTestCase):
    ITEMS = [
        SimpleNamespace(name="Spinach"),
        SimpleNamespace(name="Tomatoes"),
        SimpleNamespace(name="Paneer"),
    ]

    def clean(self, **overrides):
        recipe = make_recipe(**overrides)
        _clean_ingredient_lists([recipe], self.ITEMS)
        return recipe

    def test_copied_inventory_line_in_the_buy_list_moves_to_the_inventory_list(self):
        recipe = self.clean(
            inventory_ingredients=[],
            extra_ingredients=["Onion", "Spinach: 1 pack (expires today)"],
        )
        self.assertEqual(recipe.inventory_ingredients, ["Spinach"])
        self.assertEqual(recipe.extra_ingredients, ["Onion"])

    def test_loose_phrases_in_the_inventory_list_match_real_items(self):
        recipe = self.clean(
            inventory_ingredients=["chopped tomatoes", "PANEER (cubed)"],
            extra_ingredients=[],
        )
        self.assertEqual(recipe.inventory_ingredients, ["Tomatoes", "Paneer"])

    def test_unknown_inventory_ingredient_moves_to_the_buy_list(self):
        recipe = self.clean(
            inventory_ingredients=["Saffron", "Spinach"],
            extra_ingredients=["Onion"],
        )
        self.assertEqual(recipe.inventory_ingredients, ["Spinach"])
        self.assertEqual(recipe.extra_ingredients, ["Saffron", "Onion"])

    def test_duplicates_are_removed(self):
        recipe = self.clean(
            inventory_ingredients=["Spinach", "spinach", "Spinach (fresh)"],
            extra_ingredients=["Onion", "Onion"],
        )
        self.assertEqual(recipe.inventory_ingredients, ["Spinach"])
        self.assertEqual(recipe.extra_ingredients, ["Onion"])

    def test_loose_matching_is_not_used_for_the_buy_list(self):
        recipe = self.clean(
            inventory_ingredients=[],
            extra_ingredients=["Tomato sauce", "Chopped tomatoes"],
        )
        self.assertEqual(recipe.inventory_ingredients, [])
        self.assertEqual(recipe.extra_ingredients, ["Tomato sauce", "Chopped tomatoes"])

    def test_blank_names_are_dropped(self):
        recipe = self.clean(
            inventory_ingredients=["", "   ", "Spinach"],
            extra_ingredients=["", "Onion"],
        )
        self.assertEqual(recipe.inventory_ingredients, ["Spinach"])
        self.assertEqual(recipe.extra_ingredients, ["Onion"])


class SuggestRecipesTests(FixedDateTestCase):
    def setUp(self):
        super().setUp()
        make_item(self.alice, "Spinach", 2)
        self.items = get_usable_items(self.alice)

    def test_returns_at_most_the_requested_number_of_recipes(self):
        answer = RecipeSuggestions(
            recipes=[make_recipe(title=f"Recipe {n}") for n in range(4)]
        )
        with patch("recipes.services.generate_json", return_value=answer):
            result = suggest_recipes(self.items, preferences(count="2"))
        self.assertEqual([recipe.title for recipe in result], ["Recipe 0", "Recipe 1"])

    def test_empty_answer_raises_an_error(self):
        with patch(
            "recipes.services.generate_json",
            return_value=RecipeSuggestions(recipes=[]),
        ):
            with self.assertRaises(AIServiceError) as context:
                suggest_recipes(self.items, preferences())
        self.assertIn("did not return any recipes", str(context.exception))

    def test_prompt_and_schema_are_passed_to_the_ai(self):
        answer = RecipeSuggestions(recipes=[make_recipe()])
        with patch("recipes.services.generate_json", return_value=answer) as mocked:
            suggest_recipes(self.items, preferences())
        prompt, schema = mocked.call_args.args
        self.assertIn("Spinach", prompt)
        self.assertIs(schema, RecipeSuggestions)

    def test_ingredient_lists_are_cleaned(self):
        answer = RecipeSuggestions(
            recipes=[
                make_recipe(
                    inventory_ingredients=[],
                    extra_ingredients=["Spinach: 1 pack (expires in 2 day(s))", "Onion"],
                )
            ]
        )
        with patch("recipes.services.generate_json", return_value=answer):
            recipe = suggest_recipes(self.items, preferences())[0]
        self.assertEqual(recipe.inventory_ingredients, ["Spinach"])
        self.assertEqual(recipe.extra_ingredients, ["Onion"])

    def test_ai_errors_are_passed_on(self):
        with patch(
            "recipes.services.generate_json", side_effect=AIServiceError("boom")
        ):
            with self.assertRaises(AIServiceError) as context:
                suggest_recipes(self.items, preferences())
        self.assertEqual(str(context.exception), "boom")


class PreferencesFormTests(SimpleTestCase):
    def test_default_choices_are_valid(self):
        form = RecipePreferencesForm(preferences())
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["avoid"], "")

    def test_invalid_choices_are_rejected(self):
        cases = [
            ("diet", "carnivore"),
            ("cuisine", "Martian"),
            ("max_time", "5"),
            ("count", "9"),
            ("count", "0"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                form = RecipePreferencesForm(preferences(**{field: value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_angle_brackets_are_removed_from_the_avoid_note(self):
        form = RecipePreferencesForm(preferences(avoid="<script>alert(1)</script>"))
        self.assertTrue(form.is_valid())
        self.assertNotIn("<", form.cleaned_data["avoid"])
        self.assertNotIn(">", form.cleaned_data["avoid"])

    def test_avoid_note_longer_than_200_characters_is_rejected(self):
        form = RecipePreferencesForm(preferences(avoid="x" * 201))
        self.assertFalse(form.is_valid())
        self.assertIn("avoid", form.errors)

    def test_avoid_note_is_optional(self):
        data = preferences()
        del data["avoid"]
        form = RecipePreferencesForm(data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["avoid"], "")


@override_settings(AI_COOLDOWN_SECONDS=0)
class SuggestViewTests(FixedDateTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)
        self.url = reverse("recipes:suggest")

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_page_without_usable_food_shows_the_empty_message(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["item_count"], 0)
        self.assertContains(response, "You have no usable food in your inventory.")
        self.assertNotContains(response, 'id="recipe-form"')

    def test_page_counts_only_usable_items_of_the_logged_in_user(self):
        make_item(self.alice, "Fresh", 5)
        make_item(self.alice, "Today", 0)
        make_item(self.alice, "Stale", -1)
        make_item(self.bob, "Bob Item", 5)
        response = self.client.get(self.url)
        self.assertEqual(response.context["item_count"], 2)
        self.assertContains(response, "2 usable item(s)")
        self.assertContains(response, 'id="recipe-form"')
        self.assertIsNone(response.context["recipes"])

    def test_post_shows_recipes_and_remembers_them(self):
        make_item(self.alice, "Spinach", 2)
        answer = [make_recipe(title="Palak Paneer"), make_recipe(title="Spinach Soup")]
        with patch("recipes.views.suggest_recipes", return_value=answer):
            response = self.client.post(self.url, preferences())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Palak Paneer")
        self.assertContains(response, "Spinach Soup")
        self.assertContains(response, "These suggestions are generated by AI")
        self.assertFalse(response.context["showing_previous"])

        saved = self.client.session["suggested_recipes"]
        self.assertEqual([recipe["title"] for recipe in saved], ["Palak Paneer", "Spinach Soup"])

        usage = AIUsage.objects.get()
        self.assertEqual(usage.user, self.alice)
        self.assertEqual(usage.feature, "recipes")

    def test_post_sends_the_users_choices_and_usable_items_to_the_ai(self):
        make_item(self.alice, "Spinach", 2)
        make_item(self.alice, "Stale", -1)
        chosen = preferences(
            diet="vegan", cuisine="Indian", max_time="30", count="2", avoid="peanuts"
        )
        with patch("recipes.views.suggest_recipes", return_value=[make_recipe()]) as mocked:
            self.client.post(self.url, chosen)

        items, sent = mocked.call_args.args
        self.assertEqual([item.name for item in items], ["Spinach"])
        self.assertEqual(sent["diet"], "vegan")
        self.assertEqual(sent["cuisine"], "Indian")
        self.assertEqual(sent["max_time"], "30")
        self.assertEqual(sent["count"], "2")
        self.assertEqual(sent["avoid"], "peanuts")

    def test_ai_failure_shows_a_message_and_is_not_counted(self):
        make_item(self.alice, "Spinach", 2)
        problem = AIServiceError("The AI service is busy right now. Please try again in a moment.")
        with patch("recipes.views.suggest_recipes", side_effect=problem):
            response = self.client.post(self.url, preferences())

        self.assertContains(response, "The AI service is busy right now")
        self.assertIsNone(response.context["recipes"])
        self.assertEqual(AIUsage.objects.count(), 0)
        self.assertNotIn("suggested_recipes", self.client.session)

    @override_settings(AI_DAILY_LIMIT_PER_USER=0)
    def test_daily_limit_blocks_the_request_before_the_ai_is_called(self):
        make_item(self.alice, "Spinach", 2)
        with patch("recipes.views.suggest_recipes") as mocked:
            response = self.client.post(self.url, preferences())

        mocked.assert_not_called()
        self.assertContains(response, "AI requests for today")
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_invalid_form_does_not_call_the_ai(self):
        make_item(self.alice, "Spinach", 2)
        with patch("recipes.views.suggest_recipes") as mocked:
            response = self.client.post(self.url, preferences(diet="carnivore"))

        mocked.assert_not_called()
        self.assertIn("diet", response.context["form"].errors)
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_post_without_usable_food_does_not_call_the_ai(self):
        with patch("recipes.views.suggest_recipes") as mocked:
            response = self.client.post(self.url, preferences())

        mocked.assert_not_called()
        self.assertContains(response, "You have no usable food in your inventory.")
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_last_suggestions_are_shown_again_on_the_next_visit(self):
        make_item(self.alice, "Spinach", 2)
        session = self.client.session
        session["suggested_recipes"] = [make_recipe(title="Saved Soup").model_dump()]
        session.save()

        response = self.client.get(self.url)
        self.assertContains(response, "Saved Soup")
        self.assertContains(response, "Showing your last suggestions.")
        self.assertTrue(response.context["showing_previous"])

    def test_last_suggestions_are_hidden_when_there_is_no_usable_food(self):
        session = self.client.session
        session["suggested_recipes"] = [make_recipe(title="Saved Soup").model_dump()]
        session.save()

        response = self.client.get(self.url)
        self.assertNotContains(response, "Saved Soup")
        self.assertIsNone(response.context["recipes"])

    def test_recipe_text_is_escaped(self):
        make_item(self.alice, "Spinach", 2)
        answer = [make_recipe(title="<b>Bold</b>")]
        with patch("recipes.views.suggest_recipes", return_value=answer):
            response = self.client.post(self.url, preferences())

        self.assertNotContains(response, "<b>Bold</b>")
        self.assertContains(response, "&lt;b&gt;Bold&lt;/b&gt;")

    def test_each_recipe_has_an_add_to_plan_form(self):
        make_item(self.alice, "Spinach", 2)
        answer = [make_recipe(title="First"), make_recipe(title="Second")]
        with patch("recipes.views.suggest_recipes", return_value=answer):
            response = self.client.post(self.url, preferences())

        self.assertContains(response, reverse("planner:add_recipe"))
        self.assertContains(response, 'name="index" value="0"')
        self.assertContains(response, 'name="index" value="1"')
        self.assertContains(response, 'value="2026-11-01"')

    def test_ai_answer_is_cleaned_before_it_reaches_the_page(self):
        make_item(self.alice, "Spinach", 2)
        answer = RecipeSuggestions(
            recipes=[
                make_recipe(
                    inventory_ingredients=[],
                    extra_ingredients=["Spinach: 1 pack (expires today)", "Onion"],
                )
            ]
        )
        with patch("recipes.services.generate_json", return_value=answer):
            response = self.client.post(self.url, preferences())

        shown = response.context["recipes"][0]
        self.assertEqual(shown["inventory_ingredients"], ["Spinach"])
        self.assertEqual(shown["extra_ingredients"], ["Onion"])