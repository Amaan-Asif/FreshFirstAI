from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import FoodItem

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)


def make_item(owner, name, days_to_expiry):
    return FoodItem.objects.create(
        owner=owner,
        name=name,
        category=FoodItem.Category.OTHER,
        quantity=Decimal("1.00"),
        unit=FoodItem.Unit.PIECES,
        purchase_date=FIXED_TODAY - timedelta(days=10),
        expiry_date=FIXED_TODAY + timedelta(days=days_to_expiry),
    )


class HomePageTests(TestCase):
    def test_anonymous_visitor_sees_the_landing_page(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waste less. Eat fresh.")
        self.assertContains(response, "Get started")

    def test_logged_in_user_sees_a_dashboard_button(self):
        user = User.objects.create_user("alice", password="pass12345")
        self.client.force_login(user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Go to dashboard")
        self.assertNotContains(response, "Get started")


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.alice)

    def names_by_section(self, response):
        return {
            section["key"]: [item.name for item in section["items"]]
            for section in response.context["sections"]
        }

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        url = reverse("core:dashboard")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_items_are_sorted_into_the_right_sections(self):
        make_item(self.alice, "Old", -2)
        make_item(self.alice, "Today", 0)
        make_item(self.alice, "Boundary", 3)
        make_item(self.alice, "Later", 4)
        make_item(self.alice, "Far", 30)

        sections = self.names_by_section(self.client.get(reverse("core:dashboard")))

        self.assertCountEqual(sections["expired"], ["Old"])
        self.assertCountEqual(sections["soon"], ["Today", "Boundary"])
        self.assertCountEqual(sections["other"], ["Later", "Far"])

    def test_total_counts_all_of_the_users_items(self):
        for offset, name in enumerate(["A", "B", "C"], start=-1):
            make_item(self.alice, name, offset)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["total"], 3)

    def test_other_users_items_are_not_shown(self):
        make_item(self.bob, "Bob Item", -1)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["total"], 0)
        self.assertNotContains(response, "Bob Item")

    def test_empty_inventory_shows_friendly_messages(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["total"], 0)
        self.assertContains(response, "Nothing has expired. Great job!")