from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import FoodLog

from .services import TREND_DAYS, build_analytics

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)


def make_log(
    owner,
    name,
    action,
    category="dairy",
    unit="pcs",
    quantity="1.00",
    reason="",
    cost="0.00",
    days_ago=0,
):
    return FoodLog.objects.create(
        owner=owner,
        item_name=name,
        category=category,
        unit=unit,
        action=action,
        quantity=Decimal(quantity),
        reason=reason,
        estimated_cost=Decimal(cost),
        logged_on=FIXED_TODAY - timedelta(days=days_ago),
    )


def add_standard_logs(owner):
    """5 records: 2 consumed and 3 wasted (Bread 20 + Curd 40 + Rice 60 = 120)."""
    make_log(owner, "Milk", "consumed", unit="l", quantity="0.50")
    make_log(owner, "Milk", "consumed", unit="l", quantity="1.00")
    make_log(
        owner, "Bread", "wasted", category="grains", unit="pack",
        reason="expired", cost="20.00",
    )
    make_log(
        owner, "Curd", "wasted", category="dairy", unit="pack",
        reason="expired", cost="40.00",
    )
    make_log(
        owner, "Rice", "wasted", category="grains", unit="kg", quantity="3.00",
        reason="too_much", cost="60.00", days_ago=7,
    )


class AnalyticsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)


class BuildAnalyticsTests(AnalyticsTestCase):
    def test_returns_none_when_the_user_has_no_records(self):
        self.assertIsNone(build_analytics(self.alice))

    def test_headline_statistics(self):
        add_standard_logs(self.alice)
        stats = build_analytics(self.alice)["stats"]

        self.assertEqual(stats["total_count"], 5)
        self.assertEqual(stats["wasted_count"], 3)
        self.assertEqual(stats["consumed_count"], 2)
        self.assertEqual(stats["waste_rate"], 60.0)
        self.assertEqual(stats["total_wasted_cost"], 120.0)
        self.assertEqual(stats["average_cost"], 40.0)
        self.assertEqual(stats["top_item_name"], "Rice")
        self.assertEqual(stats["top_item_cost"], 60.0)
        self.assertEqual(stats["top_reason"], "Expired before use")
        self.assertEqual(stats["top_reason_count"], 2)

    def test_chart_data(self):
        add_standard_logs(self.alice)
        charts = build_analytics(self.alice)["charts"]

        self.assertEqual(charts["action"]["labels"], ["Consumed", "Wasted"])
        self.assertEqual(charts["action"]["values"], [2, 3])
        self.assertEqual(charts["category"]["labels"], ["Grains and bread", "Dairy"])
        self.assertEqual(charts["category"]["values"], [80.0, 40.0])
        self.assertEqual(
            charts["reason"]["labels"],
            ["Expired before use", "Bought or cooked too much"],
        )
        self.assertEqual(charts["reason"]["values"], [2, 1])

    def test_trend_covers_the_last_30_days(self):
        add_standard_logs(self.alice)
        trend = build_analytics(self.alice)["charts"]["trend"]

        self.assertEqual(len(trend["labels"]), TREND_DAYS)
        self.assertEqual(trend["labels"][0], "03 Oct")
        self.assertEqual(trend["labels"][-1], "01 Nov")
        self.assertEqual(trend["values"][-1], 60.0)  # Bread + Curd today
        self.assertEqual(trend["values"][trend["labels"].index("25 Oct")], 60.0)  # Rice
        self.assertEqual(sum(trend["values"]), 120.0)

    def test_old_waste_counts_in_totals_but_not_in_the_trend(self):
        make_log(
            self.alice, "Old Rice", "wasted", category="grains",
            reason="expired", cost="50.00", days_ago=40,
        )
        result = build_analytics(self.alice)

        self.assertEqual(result["stats"]["total_wasted_cost"], 50.0)
        self.assertEqual(sum(result["charts"]["trend"]["values"]), 0.0)

    def test_user_with_only_consumed_records(self):
        make_log(self.alice, "Milk", "consumed", unit="l")
        result = build_analytics(self.alice)
        stats = result["stats"]

        self.assertEqual(stats["waste_rate"], 0.0)
        self.assertEqual(stats["total_wasted_cost"], 0.0)
        self.assertEqual(stats["average_cost"], 0.0)
        self.assertIsNone(stats["top_item_name"])
        self.assertIsNone(stats["top_reason"])
        self.assertEqual(result["charts"]["category"]["labels"], [])
        self.assertEqual(result["charts"]["reason"]["labels"], [])

    def test_other_users_records_are_ignored(self):
        add_standard_logs(self.alice)
        make_log(
            self.bob, "Secret Truffle", "wasted", category="other",
            reason="spoiled", cost="500.00",
        )
        stats = build_analytics(self.alice)["stats"]

        self.assertEqual(stats["total_count"], 5)
        self.assertEqual(stats["total_wasted_cost"], 120.0)
        self.assertEqual(stats["top_item_name"], "Rice")


class AnalyticsPageTests(AnalyticsTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        url = reverse("analytics:dashboard")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_user_without_records_sees_the_empty_message(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(response, "No records yet.")

    def test_page_shows_the_statistics_and_chart_data(self):
        add_standard_logs(self.alice)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("analytics:dashboard"))

        self.assertContains(response, "60.0%")
        self.assertContains(response, "₹120.00")
        self.assertContains(response, "Rice")
        self.assertContains(response, "Expired before use")
        self.assertContains(response, 'id="charts-data"')
        self.assertContains(response, "Generate insights")

    def test_page_never_shows_another_users_data(self):
        add_standard_logs(self.alice)
        make_log(
            self.bob, "Secret Truffle", "wasted", category="other",
            reason="spoiled", cost="999.00",
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertNotContains(response, "Secret Truffle")
        self.assertNotContains(response, "999")

    def test_insights_card_explains_the_three_record_rule(self):
        make_log(self.alice, "Milk", "consumed", unit="l")
        self.client.force_login(self.alice)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(response, "You need at least 3 records first (you have 1)")