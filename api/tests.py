from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from inventory.models import FoodItem, FoodLog

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)


def make_item(owner, name="Milk", days_to_expiry=10, **overrides):
    values = {
        "owner": owner,
        "name": name,
        "category": FoodItem.Category.DAIRY,
        "quantity": Decimal("2.00"),
        "unit": FoodItem.Unit.LITRES,
        "purchase_date": FIXED_TODAY - timedelta(days=3),
        "expiry_date": FIXED_TODAY + timedelta(days=days_to_expiry),
    }
    values.update(overrides)
    return FoodItem.objects.create(**values)


def make_log(owner, name="Milk", action="consumed", **overrides):
    values = {
        "owner": owner,
        "item_name": name,
        "category": "dairy",
        "unit": "pcs",
        "action": action,
        "quantity": Decimal("1.00"),
        "reason": "",
        "estimated_cost": Decimal("0.00"),
        "logged_on": FIXED_TODAY,
    }
    values.update(overrides)
    return FoodLog.objects.create(**values)


def item_payload(**overrides):
    data = {
        "name": "Bananas",
        "category": "fruits",
        "quantity": "6",
        "unit": "pcs",
        "purchase_date": "2026-11-01",
        "expiry_date": "2026-11-05",
        "storage_notes": "On the counter",
    }
    data.update(overrides)
    return data


def names(response):
    return [row["name"] for row in response.json()["results"]]


class ApiTestCase(APITestCase):
    """Creates two users, fixes today's date, and signs in as alice."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        cache.clear()  # forget earlier rate-limit counters
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(user=self.alice)
        self.list_url = reverse("api:inventory-list")


class AccessTests(ApiTestCase):
    def test_anonymous_requests_are_refused_on_every_endpoint(self):
        item = make_item(self.alice)
        log = make_log(self.alice)
        self.client.force_authenticate(user=None)
        urls = [
            reverse("api:api-root"),
            reverse("api:inventory-list"),
            reverse("api:inventory-detail", args=[item.pk]),
            reverse("api:inventory-expiring"),
            reverse("api:logs-list"),
            reverse("api:logs-detail", args=[log.pk]),
            reverse("api:analytics-summary"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_anonymous_user_cannot_create_an_item(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.list_url, item_payload(), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FoodItem.objects.exists())

    def test_anonymous_user_cannot_change_or_delete_an_item(self):
        item = make_item(self.alice)
        url = reverse("api:inventory-detail", args=[item.pk])
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.put(url, item_payload(), format="json").status_code, 403
        )
        self.assertEqual(
            self.client.patch(url, {"quantity": "9"}, format="json").status_code, 403
        )
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertTrue(FoodItem.objects.filter(pk=item.pk).exists())


class InventoryListTests(ApiTestCase):
    def test_list_shows_only_own_items(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.bob, "Secret Cheese")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(names(response), ["Almond Milk"])

    def test_item_fields_include_status_and_hide_the_owner(self):
        make_item(self.alice, "Milk", days_to_expiry=2)
        row = self.client.get(self.list_url).json()["results"][0]
        self.assertEqual(
            set(row),
            {
                "id", "name", "category", "category_display", "quantity", "unit",
                "purchase_date", "expiry_date", "storage_notes", "status",
                "days_until_expiry", "created_at", "updated_at",
            },
        )
        self.assertNotIn("owner", row)
        self.assertEqual(row["status"], "expiring_soon")
        self.assertEqual(row["days_until_expiry"], 2)
        self.assertEqual(row["category_display"], "Dairy")
        self.assertEqual(row["quantity"], "2.00")

    def test_list_is_sorted_by_expiry_date_by_default(self):
        make_item(self.alice, "Apple", 9)
        make_item(self.alice, "Banana", 5)
        make_item(self.alice, "Cherry", 1)
        self.assertEqual(
            names(self.client.get(self.list_url)), ["Cherry", "Banana", "Apple"]
        )

    def test_ordering_can_be_changed(self):
        make_item(self.alice, "Apple", 9)
        make_item(self.alice, "Banana", 5)
        make_item(self.alice, "Cherry", 1)
        by_name = self.client.get(self.list_url, {"ordering": "name"})
        self.assertEqual(names(by_name), ["Apple", "Banana", "Cherry"])
        by_name_reversed = self.client.get(self.list_url, {"ordering": "-name"})
        self.assertEqual(names(by_name_reversed), ["Cherry", "Banana", "Apple"])

    def test_results_are_paginated(self):
        FoodItem.objects.bulk_create(
            [
                FoodItem(
                    owner=self.alice,
                    name=f"Item {number:02d}",
                    category="other",
                    quantity=Decimal("1.00"),
                    unit="pcs",
                    purchase_date=FIXED_TODAY - timedelta(days=1),
                    expiry_date=FIXED_TODAY + timedelta(days=number),
                )
                for number in range(25)
            ]
        )
        first_page = self.client.get(self.list_url).json()
        self.assertEqual(first_page["count"], 25)
        self.assertEqual(len(first_page["results"]), 20)
        self.assertIsNotNone(first_page["next"])
        second_page = self.client.get(self.list_url, {"page": 2}).json()
        self.assertEqual(len(second_page["results"]), 5)
        self.assertIsNone(second_page["next"])

    def test_search_by_name_ignores_case(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.alice, "Basmati Rice")
        response = self.client.get(self.list_url, {"search": "MILK"})
        self.assertEqual(names(response), ["Almond Milk"])

    def test_category_filter(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.alice, "Bananas", category=FoodItem.Category.FRUITS)
        response = self.client.get(self.list_url, {"category": "fruits"})
        self.assertEqual(names(response), ["Bananas"])

    def test_unknown_category_is_rejected(self):
        response = self.client.get(self.list_url, {"category": "candy"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.json())

    def test_status_filters(self):
        make_item(self.alice, "Old", -2)
        make_item(self.alice, "Today", 0)
        make_item(self.alice, "Boundary", 3)
        make_item(self.alice, "Later", 4)
        make_item(self.alice, "Far", 30)
        expected = {
            "expired": ["Old"],
            "expiring_soon": ["Today", "Boundary"],
            "fresh": ["Later", "Far"],
        }
        for status, expected_names in expected.items():
            with self.subTest(status=status):
                response = self.client.get(self.list_url, {"status": status})
                self.assertEqual(names(response), expected_names)

    def test_unknown_status_is_rejected(self):
        response = self.client.get(self.list_url, {"status": "nonsense"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_expiring_shortcut_lists_only_items_expiring_soon(self):
        make_item(self.alice, "Old", -2)
        make_item(self.alice, "Today", 0)
        make_item(self.alice, "Boundary", 3)
        make_item(self.alice, "Later", 4)
        make_item(self.bob, "Bob Soon", 1)
        response = self.client.get(reverse("api:inventory-expiring"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["name"] for row in response.json()], ["Today", "Boundary"])


class CreateTests(ApiTestCase):
    def test_valid_item_is_created_for_the_logged_in_user(self):
        response = self.client.post(self.list_url, item_payload(), format="json")
        self.assertEqual(response.status_code, 201)
        item = FoodItem.objects.get()
        self.assertEqual(item.owner, self.alice)
        body = response.json()
        self.assertEqual(body["id"], item.pk)
        self.assertEqual(body["quantity"], "6.00")
        self.assertEqual(body["category_display"], "Fruits")
        self.assertEqual(body["status"], "fresh")
        self.assertEqual(body["days_until_expiry"], 4)

    def test_owner_in_the_request_is_ignored(self):
        payload = item_payload(owner=self.bob.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FoodItem.objects.get().owner, self.alice)

    def test_read_only_fields_are_ignored(self):
        payload = item_payload(id=9999, status="expired", days_until_expiry=-5)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertNotEqual(body["id"], 9999)
        self.assertEqual(body["status"], "fresh")
        self.assertEqual(body["days_until_expiry"], 4)

    def test_expiry_before_purchase_is_rejected(self):
        payload = item_payload(purchase_date="2026-11-05", expiry_date="2026-11-01")
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["expiry_date"],
            ["Expiry date cannot be before the purchase date."],
        )
        self.assertFalse(FoodItem.objects.exists())

    def test_invalid_values_are_rejected(self):
        cases = [
            ("zero quantity", {"quantity": "0"}, None, "quantity"),
            ("negative quantity", {"quantity": "-2"}, None, "quantity"),
            ("bad category", {"category": "candy"}, None, "category"),
            ("bad unit", {"unit": "bucket"}, None, "unit"),
            ("blank name", {"name": "   "}, None, "name"),
            ("missing name", {}, "name", "name"),
            ("missing expiry date", {}, "expiry_date", "expiry_date"),
        ]
        for label, changes, missing_key, error_field in cases:
            with self.subTest(case=label):
                payload = item_payload(**changes)
                if missing_key:
                    del payload[missing_key]
                response = self.client.post(self.list_url, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(error_field, response.json())
        self.assertFalse(FoodItem.objects.exists())


class DetailTests(ApiTestCase):
    def test_user_can_read_own_item(self):
        item = make_item(self.alice, "Almond Milk")
        response = self.client.get(reverse("api:inventory-detail", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Almond Milk")

    def test_cannot_read_another_users_item(self):
        item = make_item(self.bob, "Secret Cheese")
        response = self.client.get(reverse("api:inventory-detail", args=[item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_put_replaces_the_item(self):
        item = make_item(self.alice, "Milk")
        url = reverse("api:inventory-detail", args=[item.pk])
        payload = item_payload(
            name="Oat Milk", quantity="3", purchase_date="2026-10-29",
            expiry_date="2026-11-20",
        )
        response = self.client.put(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.name, "Oat Milk")
        self.assertEqual(item.quantity, Decimal("3.00"))
        self.assertEqual(item.owner, self.alice)

    def test_patch_changes_only_some_fields(self):
        item = make_item(self.alice, "Milk")
        url = reverse("api:inventory-detail", args=[item.pk])
        response = self.client.patch(url, {"quantity": "1.5"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("1.50"))
        self.assertEqual(item.name, "Milk")

    def test_patch_cannot_set_expiry_before_purchase(self):
        item = make_item(self.alice, "Milk")  # bought on 2026-10-29
        url = reverse("api:inventory-detail", args=[item.pk])
        response = self.client.patch(url, {"expiry_date": "2026-10-20"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expiry_date", response.json())
        item.refresh_from_db()
        self.assertEqual(item.expiry_date, FIXED_TODAY + timedelta(days=10))

    def test_cannot_change_another_users_item(self):
        item = make_item(self.bob, "Secret Cheese")
        url = reverse("api:inventory-detail", args=[item.pk])
        self.assertEqual(
            self.client.put(url, item_payload(), format="json").status_code, 404
        )
        self.assertEqual(
            self.client.patch(url, {"name": "Hacked"}, format="json").status_code, 404
        )
        item.refresh_from_db()
        self.assertEqual(item.name, "Secret Cheese")

    def test_user_can_delete_own_item(self):
        item = make_item(self.alice)
        response = self.client.delete(reverse("api:inventory-detail", args=[item.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(FoodItem.objects.filter(pk=item.pk).exists())

    def test_cannot_delete_another_users_item(self):
        item = make_item(self.bob)
        response = self.client.delete(reverse("api:inventory-detail", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FoodItem.objects.filter(pk=item.pk).exists())


class LogTests(ApiTestCase):
    def test_list_shows_only_own_logs(self):
        make_log(self.alice, "Alice Soup")
        make_log(self.bob, "Bob Stew")
        response = self.client.get(reverse("api:logs-list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["item_name"], "Alice Soup")

    def test_action_filter(self):
        make_log(self.alice, "Milk", "consumed")
        make_log(self.alice, "Bread", "wasted", reason="expired")
        response = self.client.get(reverse("api:logs-list"), {"action": "wasted"})
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["item_name"], "Bread")
        self.assertEqual(data["results"][0]["reason_display"], "Expired before use")

    def test_unknown_action_is_rejected(self):
        response = self.client.get(reverse("api:logs-list"), {"action": "stolen"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("action", response.json())

    def test_logs_are_read_only(self):
        log = make_log(self.alice)
        list_url = reverse("api:logs-list")
        detail_url = reverse("api:logs-detail", args=[log.pk])
        self.assertEqual(self.client.post(list_url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.put(detail_url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail_url).status_code, 405)
        self.assertTrue(FoodLog.objects.filter(pk=log.pk).exists())

    def test_cannot_read_another_users_log(self):
        log = make_log(self.bob)
        response = self.client.get(reverse("api:logs-detail", args=[log.pk]))
        self.assertEqual(response.status_code, 404)


class AnalyticsSummaryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("api:analytics-summary")

    def test_user_without_records(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"has_data": False, "stats": None, "charts": None}
        )

    def add_standard_logs(self, owner):
        make_log(owner, "Milk", "consumed", unit="l", quantity="0.50")
        make_log(owner, "Milk", "consumed", unit="l", quantity="1.00")
        make_log(owner, "Bread", "wasted", category="grains", unit="pack",
                 reason="expired", estimated_cost=Decimal("20.00"))
        make_log(owner, "Curd", "wasted", category="dairy", unit="pack",
                 reason="expired", estimated_cost=Decimal("40.00"))
        make_log(owner, "Rice", "wasted", category="grains", unit="kg",
                 quantity="3.00", reason="too_much",
                 estimated_cost=Decimal("60.00"))

    def test_summary_matches_the_records(self):
        self.add_standard_logs(self.alice)
        body = self.client.get(self.url).json()
        stats = body["stats"]
        self.assertTrue(body["has_data"])
        self.assertEqual(stats["total_count"], 5)
        self.assertEqual(stats["wasted_count"], 3)
        self.assertEqual(stats["consumed_count"], 2)
        self.assertEqual(stats["waste_rate"], 60.0)
        self.assertEqual(stats["total_wasted_cost"], 120.0)
        self.assertEqual(stats["top_item_name"], "Rice")
        self.assertEqual(stats["top_reason"], "Expired before use")
        self.assertEqual(body["charts"]["action"]["values"], [2, 3])
        self.assertEqual(len(body["charts"]["trend"]["labels"]), 30)

    def test_other_users_records_are_ignored(self):
        self.add_standard_logs(self.alice)
        make_log(self.bob, "Secret Truffle", "wasted", category="other",
                 reason="spoiled", estimated_cost=Decimal("500.00"))
        stats = self.client.get(self.url).json()["stats"]
        self.assertEqual(stats["total_count"], 5)
        self.assertEqual(stats["total_wasted_cost"], 120.0)
        self.assertEqual(stats["top_item_name"], "Rice")