from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import FoodItem, FoodLog

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


def item_form_data(**overrides):
    data = {
        "name": "Yogurt",
        "category": "dairy",
        "quantity": "2",
        "unit": "pcs",
        "purchase_date": "2026-11-01",
        "expiry_date": "2026-11-10",
        "storage_notes": "",
    }
    data.update(overrides)
    return data


def log_form_data(**overrides):
    data = {
        "action": "consumed",
        "quantity": "1",
        "reason": "",
        "estimated_cost": "",
        "logged_on": "2026-11-01",
    }
    data.update(overrides)
    return data


class ViewTestCase(TestCase):
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


class AccessTests(ViewTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        item = make_item(self.alice)
        self.client.logout()
        urls = [
            reverse("inventory:list"),
            reverse("inventory:add"),
            reverse("inventory:history"),
            reverse("inventory:edit", args=[item.pk]),
            reverse("inventory:delete", args=[item.pk]),
            reverse("inventory:log", args=[item.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('accounts:login')}?next={url}"
                )


class InventoryListTests(ViewTestCase):
    def test_list_shows_only_own_items(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.bob, "Secret Cheese")
        response = self.client.get(reverse("inventory:list"))
        self.assertContains(response, "Almond Milk")
        self.assertNotContains(response, "Secret Cheese")

    def test_search_by_name_ignores_case(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.alice, "Basmati Rice")
        response = self.client.get(reverse("inventory:list"), {"q": "MILK"})
        self.assertContains(response, "Almond Milk")
        self.assertNotContains(response, "Basmati Rice")

    def test_category_filter(self):
        make_item(self.alice, "Almond Milk")
        make_item(self.alice, "Basmati Rice", category=FoodItem.Category.GRAINS)
        response = self.client.get(reverse("inventory:list"), {"category": "grains"})
        self.assertContains(response, "Basmati Rice")
        self.assertNotContains(response, "Almond Milk")

    def test_expired_status_filter(self):
        make_item(self.alice, "Stale Bread", days_to_expiry=-2)
        make_item(self.alice, "Fresh Apples", days_to_expiry=10)
        response = self.client.get(reverse("inventory:list"), {"status": "expired"})
        self.assertContains(response, "Stale Bread")
        self.assertNotContains(response, "Fresh Apples")


class InventoryEditTests(ViewTestCase):
    def test_create_item_sets_owner_to_logged_in_user(self):
        response = self.client.post(reverse("inventory:add"), item_form_data())
        self.assertRedirects(response, reverse("inventory:list"))
        item = FoodItem.objects.get(name="Yogurt")
        self.assertEqual(item.owner, self.alice)

    def test_create_rejects_expiry_before_purchase(self):
        data = item_form_data(purchase_date="2026-11-05", expiry_date="2026-11-01")
        response = self.client.post(reverse("inventory:add"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expiry date cannot be before the purchase date.")
        self.assertFalse(FoodItem.objects.exists())

    def test_user_can_edit_own_item(self):
        item = make_item(self.alice)
        data = item_form_data(name="Oat Milk", quantity="3")
        self.client.post(reverse("inventory:edit", args=[item.pk]), data)
        item.refresh_from_db()
        self.assertEqual(item.name, "Oat Milk")
        self.assertEqual(item.quantity, Decimal("3.00"))

    def test_user_can_delete_own_item(self):
        item = make_item(self.alice)
        response = self.client.post(reverse("inventory:delete", args=[item.pk]))
        self.assertRedirects(response, reverse("inventory:list"))
        self.assertFalse(FoodItem.objects.filter(pk=item.pk).exists())

    def test_cannot_open_edit_page_of_another_users_item(self):
        bobs_item = make_item(self.bob, "Cheese")
        response = self.client.get(reverse("inventory:edit", args=[bobs_item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_users_item(self):
        bobs_item = make_item(self.bob, "Cheese")
        response = self.client.post(reverse("inventory:delete", args=[bobs_item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FoodItem.objects.filter(pk=bobs_item.pk).exists())


class LogItemTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.item = make_item(self.alice, "Milk", quantity=Decimal("2.00"))
        self.url = reverse("inventory:log", args=[self.item.pk])

    def test_using_part_of_an_item_reduces_its_quantity(self):
        response = self.client.post(self.url, log_form_data(quantity="0.5"))
        self.assertRedirects(response, reverse("inventory:list"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("1.50"))
        log = FoodLog.objects.get()
        self.assertEqual(log.action, "consumed")
        self.assertEqual(log.owner, self.alice)

    def test_using_everything_removes_the_item_but_keeps_the_history(self):
        self.client.post(self.url, log_form_data(quantity="2"))
        self.assertFalse(FoodItem.objects.filter(pk=self.item.pk).exists())
        log = FoodLog.objects.get()
        self.assertEqual(log.item_name, "Milk")
        self.assertIsNone(log.food_item)

    def test_cannot_log_more_than_is_available(self):
        response = self.client.post(self.url, log_form_data(quantity="5"))
        self.assertContains(response, "You only have")
        self.assertFalse(FoodLog.objects.exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("2.00"))

    def test_waste_needs_a_reason(self):
        response = self.client.post(
            self.url, log_form_data(action="wasted", reason="")
        )
        self.assertContains(response, "Please choose a reason for the waste.")
        self.assertFalse(FoodLog.objects.exists())

    def test_waste_is_recorded_with_reason_and_cost(self):
        data = log_form_data(
            action="wasted", reason="expired", quantity="1", estimated_cost="25"
        )
        self.client.post(self.url, data)
        log = FoodLog.objects.get()
        self.assertEqual(log.reason, "expired")
        self.assertEqual(log.estimated_cost, Decimal("25.00"))

    def test_future_date_is_rejected(self):
        response = self.client.post(self.url, log_form_data(logged_on="2026-11-05"))
        self.assertContains(response, "The date cannot be in the future.")
        self.assertFalse(FoodLog.objects.exists())

    def test_cannot_log_against_another_users_item(self):
        bobs_item = make_item(self.bob, "Cheese")
        response = self.client.post(
            reverse("inventory:log", args=[bobs_item.pk]), log_form_data()
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(FoodLog.objects.exists())


class HistoryTests(ViewTestCase):
    def test_history_shows_only_own_records(self):
        for owner, name in ((self.alice, "Alice Soup"), (self.bob, "Bob Stew")):
            FoodLog.objects.create(
                owner=owner,
                item_name=name,
                category="dairy",
                unit="l",
                action="consumed",
                quantity=Decimal("1.00"),
                logged_on=FIXED_TODAY,
            )
        response = self.client.get(reverse("inventory:history"))
        self.assertContains(response, "Alice Soup")
        self.assertNotContains(response, "Bob Stew")