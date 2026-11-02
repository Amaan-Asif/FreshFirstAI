from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from assistant.client import AIServiceError
from assistant.models import AIUsage
from inventory.models import FoodLog

from .insights import (
    WasteInsight,
    build_insight_input,
    build_prompt,
    generate_waste_insight,
)

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)

INSIGHT = WasteInsight(
    summary="You are doing well.",
    patterns=["Rice is your top waste."],
    suggestions=["Cook smaller portions."],
)


def sample_data():
    """Hand-made analytics data with figures that are easy to check."""
    trend_values = [0.0] * 30
    trend_values[-1] = 60.0   # last 7 days: 60 + 15 = 75
    trend_values[-5] = 15.0
    trend_values[-8] = 30.0   # previous 7 days: 30 + 5 = 35
    trend_values[-14] = 5.0
    return {
        "stats": {
            "total_count": 5,
            "wasted_count": 3,
            "consumed_count": 2,
            "waste_rate": 60.0,
            "total_wasted_cost": 120.0,
            "average_cost": 40.0,
            "top_item_name": "Rice",
            "top_item_cost": 60.0,
            "top_reason": "Expired before use",
            "top_reason_count": 2,
        },
        "charts": {
            "category": {"labels": ["Grains and bread", "Dairy"], "values": [80.0, 40.0]},
            "reason": {
                "labels": ["Expired before use", "Bought or cooked too much"],
                "values": [2, 1],
            },
            "trend": {
                "labels": [f"Day {number}" for number in range(30)],
                "values": trend_values,
            },
        },
    }


def make_log(owner, name, action, cost="0.00", reason=""):
    return FoodLog.objects.create(
        owner=owner,
        item_name=name,
        category="dairy",
        unit="pcs",
        action=action,
        quantity=Decimal("1.00"),
        reason=reason,
        estimated_cost=Decimal(cost),
        logged_on=FIXED_TODAY,
    )


def add_three_logs(owner):
    """3 records: 1 consumed and 2 wasted (Bread 20 + Rice 60 = 80)."""
    make_log(owner, "Milk", "consumed")
    make_log(owner, "Bread", "wasted", cost="20.00", reason="expired")
    make_log(owner, "Rice", "wasted", cost="60.00", reason="too_much")


class BuildInsightInputTests(SimpleTestCase):
    def test_summary_has_the_expected_figures(self):
        summary = build_insight_input(sample_data())
        self.assertEqual(
            summary,
            {
                "total_records": 5,
                "consumed_records": 2,
                "wasted_records": 3,
                "waste_rate_percent": 60.0,
                "total_money_wasted_rupees": 120.0,
                "average_cost_per_waste_rupees": 40.0,
                "most_wasted_item": {"name": "Rice", "money_wasted_rupees": 60.0},
                "most_common_reason": {"reason": "Expired before use", "times": 2},
                "money_wasted_by_category_rupees": {
                    "Grains and bread": 80.0,
                    "Dairy": 40.0,
                },
                "times_wasted_by_reason": {
                    "Expired before use": 2,
                    "Bought or cooked too much": 1,
                },
                "money_wasted_last_7_days_rupees": 75.0,
                "money_wasted_previous_7_days_rupees": 35.0,
            },
        )

    def test_summary_has_only_the_expected_keys(self):
        # Nothing personal (no username, email or item notes) is ever included.
        summary = build_insight_input(sample_data())
        self.assertEqual(
            set(summary),
            {
                "total_records", "consumed_records", "wasted_records",
                "waste_rate_percent", "total_money_wasted_rupees",
                "average_cost_per_waste_rupees", "most_wasted_item",
                "most_common_reason", "money_wasted_by_category_rupees",
                "times_wasted_by_reason", "money_wasted_last_7_days_rupees",
                "money_wasted_previous_7_days_rupees",
            },
        )

    def test_missing_top_item_and_reason_become_none(self):
        data = sample_data()
        data["stats"]["top_item_name"] = None
        data["stats"]["top_reason"] = None
        summary = build_insight_input(data)
        self.assertIsNone(summary["most_wasted_item"])
        self.assertIsNone(summary["most_common_reason"])

    def test_short_trend_is_handled(self):
        data = sample_data()
        data["charts"]["trend"]["values"] = [10.0, 5.0, 1.0]
        summary = build_insight_input(data)
        self.assertEqual(summary["money_wasted_last_7_days_rupees"], 16.0)
        self.assertEqual(summary["money_wasted_previous_7_days_rupees"], 0)


class BuildPromptTests(SimpleTestCase):
    def test_prompt_contains_the_statistics_as_json(self):
        prompt = build_prompt(build_insight_input(sample_data()))
        self.assertIn('"waste_rate_percent": 60.0', prompt)
        self.assertIn('"name": "Rice"', prompt)
        self.assertIn('"total_records": 5', prompt)

    def test_prompt_keeps_non_ascii_characters(self):
        prompt = build_prompt({"category": "Café"})
        self.assertIn("Café", prompt)
        self.assertNotIn("\\u00e9", prompt)

    def test_prompt_asks_for_all_three_parts_and_forbids_inventing(self):
        prompt = build_prompt(build_insight_input(sample_data()))
        self.assertIn("- summary:", prompt)
        self.assertIn("- patterns:", prompt)
        self.assertIn("- suggestions:", prompt)
        self.assertIn("Do not invent figures", prompt)
        self.assertIn("rupees", prompt)


class GenerateInsightTests(SimpleTestCase):
    def generate(self, answer):
        with patch("analytics.insights.generate_json", return_value=answer):
            return generate_waste_insight(sample_data())

    def test_returns_the_ai_answer(self):
        result = self.generate(INSIGHT)
        self.assertEqual(result.summary, "You are doing well.")
        self.assertEqual(result.patterns, ["Rice is your top waste."])
        self.assertEqual(result.suggestions, ["Cook smaller portions."])

    def test_blank_entries_are_removed_and_text_is_trimmed(self):
        answer = WasteInsight(
            summary="  You are doing well.  ",
            patterns=["  Pattern A ", "", "   "],
            suggestions=[" Tip 1 ", "", "Tip 2"],
        )
        result = self.generate(answer)
        self.assertEqual(result.patterns, ["Pattern A"])
        self.assertEqual(result.suggestions, ["Tip 1", "Tip 2"])

    def test_lists_are_limited_to_five_entries(self):
        answer = WasteInsight(
            summary="Summary.",
            patterns=[f"Pattern {number}" for number in range(8)],
            suggestions=[f"Tip {number}" for number in range(7)],
        )
        result = self.generate(answer)
        self.assertEqual(len(result.patterns), 5)
        self.assertEqual(len(result.suggestions), 5)

    def test_blank_summary_is_rejected(self):
        answer = WasteInsight(summary="   ", patterns=["A"], suggestions=["B"])
        with self.assertRaises(AIServiceError) as context:
            self.generate(answer)
        self.assertIn("incomplete", str(context.exception))

    def test_missing_suggestions_are_rejected(self):
        answer = WasteInsight(summary="Summary.", patterns=["A"], suggestions=["", "  "])
        with self.assertRaises(AIServiceError) as context:
            self.generate(answer)
        self.assertIn("incomplete", str(context.exception))

    def test_prompt_and_schema_are_passed_to_the_ai(self):
        with patch("analytics.insights.generate_json", return_value=INSIGHT) as mocked:
            generate_waste_insight(sample_data())
        prompt, schema = mocked.call_args.args
        self.assertIn("Rice", prompt)
        self.assertIn('"total_records": 5', prompt)
        self.assertIs(schema, WasteInsight)

    def test_ai_errors_are_passed_on(self):
        with patch(
            "analytics.insights.generate_json", side_effect=AIServiceError("boom")
        ):
            with self.assertRaises(AIServiceError) as context:
                generate_waste_insight(sample_data())
        self.assertEqual(str(context.exception), "boom")


@override_settings(AI_COOLDOWN_SECONDS=0)
class GenerateInsightViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.alice)
        self.url = reverse("analytics:insights")

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_get_request_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_too_few_records_skip_the_ai(self):
        make_log(self.alice, "Milk", "consumed")
        make_log(self.alice, "Bread", "wasted", cost="20.00", reason="expired")
        with patch("analytics.views.generate_waste_insight") as mocked:
            response = self.client.post(self.url, follow=True)

        mocked.assert_not_called()
        self.assertContains(
            response,
            "Record at least 3 items as consumed or wasted before generating insights.",
        )
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_no_records_skip_the_ai(self):
        with patch("analytics.views.generate_waste_insight") as mocked:
            response = self.client.post(self.url, follow=True)

        mocked.assert_not_called()
        self.assertContains(
            response,
            "Record at least 3 items as consumed or wasted before generating insights.",
        )
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_success_stores_and_shows_the_insight(self):
        add_three_logs(self.alice)
        with patch("analytics.views.generate_waste_insight", return_value=INSIGHT):
            response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse("analytics:dashboard"))
        self.assertContains(response, "Your insights are ready.")
        self.assertContains(response, "You are doing well.")
        self.assertContains(response, "Rice is your top waste.")
        self.assertContains(response, "Cook smaller portions.")

        stored = self.client.session["waste_insight"]
        self.assertEqual(stored["summary"], "You are doing well.")
        self.assertEqual(stored["patterns"], ["Rice is your top waste."])
        self.assertEqual(stored["suggestions"], ["Cook smaller portions."])
        self.assertIn("generated_at", stored)

        usage = AIUsage.objects.get()
        self.assertEqual(usage.user, self.alice)
        self.assertEqual(usage.feature, "insights")

    def test_ai_receives_only_the_users_own_figures(self):
        add_three_logs(self.alice)
        add_three_logs(self.bob)
        make_log(self.bob, "Truffle", "wasted", cost="500.00", reason="spoiled")
        with patch(
            "analytics.views.generate_waste_insight", return_value=INSIGHT
        ) as mocked:
            self.client.post(self.url)

        data = mocked.call_args.args[0]
        self.assertEqual(data["stats"]["total_count"], 3)
        self.assertEqual(data["stats"]["total_wasted_cost"], 80.0)
        self.assertEqual(data["stats"]["top_item_name"], "Rice")

    def test_ai_failure_is_reported_and_not_counted(self):
        add_three_logs(self.alice)
        problem = AIServiceError(
            "The AI service is busy right now. Please try again in a moment."
        )
        with patch("analytics.views.generate_waste_insight", side_effect=problem):
            response = self.client.post(self.url, follow=True)

        self.assertContains(response, "The AI service is busy right now")
        self.assertEqual(AIUsage.objects.count(), 0)
        self.assertNotIn("waste_insight", self.client.session)

    @override_settings(AI_DAILY_LIMIT_PER_USER=0)
    def test_daily_limit_blocks_before_the_ai_is_called(self):
        add_three_logs(self.alice)
        with patch("analytics.views.generate_waste_insight") as mocked:
            response = self.client.post(self.url, follow=True)

        mocked.assert_not_called()
        self.assertContains(response, "AI requests for today")
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_regenerating_replaces_the_insight(self):
        add_three_logs(self.alice)
        second = WasteInsight(
            summary="A fresh take.",
            patterns=["A new pattern."],
            suggestions=["A new tip."],
        )
        with patch(
            "analytics.views.generate_waste_insight", side_effect=[INSIGHT, second]
        ):
            self.client.post(self.url, follow=True)
            response = self.client.post(self.url, follow=True)

        self.assertContains(response, "A fresh take.")
        self.assertNotContains(response, "You are doing well.")
        self.assertEqual(self.client.session["waste_insight"]["summary"], "A fresh take.")
        self.assertEqual(AIUsage.objects.count(), 2)


class DashboardInsightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        add_three_logs(self.alice)
        self.client.force_login(self.alice)
        self.url = reverse("analytics:dashboard")

    def store_insight(self, summary="Stored summary."):
        session = self.client.session
        session["waste_insight"] = {
            "summary": summary,
            "patterns": ["Stored pattern."],
            "suggestions": ["Stored tip."],
            "generated_at": "01 Nov 2026, 09:00 AM",
        }
        session.save()

    def test_stored_insight_is_shown_with_a_regenerate_button(self):
        self.store_insight()
        response = self.client.get(self.url)
        self.assertContains(response, "Stored summary.")
        self.assertContains(response, "Stored pattern.")
        self.assertContains(response, "Stored tip.")
        self.assertContains(response, "Generated 01 Nov 2026, 09:00 AM")
        self.assertContains(response, "Regenerate insights")
        self.assertNotContains(response, "Generate insights")

    def test_without_an_insight_the_generate_button_is_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Generate insights")
        self.assertNotContains(response, "Regenerate insights")

    def test_insight_text_is_escaped(self):
        self.store_insight(summary="<b>Bold</b>")
        response = self.client.get(self.url)
        self.assertNotContains(response, "<b>Bold</b>")
        self.assertContains(response, "&lt;b&gt;Bold&lt;/b&gt;")

    def test_insight_is_not_shown_to_another_user(self):
        self.store_insight()
        self.client.logout()
        add_three_logs(self.bob)
        self.client.force_login(self.bob)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Stored summary.")
        self.assertContains(response, "Generate insights")