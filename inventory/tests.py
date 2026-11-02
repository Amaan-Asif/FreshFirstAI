from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import EXPIRING_SOON_DAYS, FoodItem

User = get_user_model()

# Every test pretends that today is this date, so results never change.
FIXED_TODAY = date(2026, 11, 1)


def build_item(user, expiry_offset, **overrides):
    """Make an unsaved FoodItem that expires `expiry_offset` days from FIXED_TODAY."""
    values = {
        "owner": user,
        "name": "Milk",
        "category": FoodItem.Category.DAIRY,
        "quantity": Decimal("1.00"),
        "unit": FoodItem.Unit.LITRES,
        "purchase_date": FIXED_TODAY - timedelta(days=5),
        "expiry_date": FIXED_TODAY + timedelta(days=expiry_offset),
    }
    values.update(overrides)
    return FoodItem(**values)


class FoodItemStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("tester", password="pass12345")

    def setUp(self):
        patcher = patch("django.utils.timezone.localdate", return_value=FIXED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_item_that_expired_yesterday_is_expired(self):
        item = build_item(self.user, -1)
        self.assertEqual(item.days_until_expiry, -1)
        self.assertEqual(item.status, "expired")

    def test_item_expiring_today_is_expiring_soon(self):
        item = build_item(self.user, 0)
        self.assertEqual(item.days_until_expiry, 0)
        self.assertEqual(item.status, "expiring_soon")

    def test_item_on_the_soon_boundary_is_expiring_soon(self):
        item = build_item(self.user, EXPIRING_SOON_DAYS)
        self.assertEqual(item.status, "expiring_soon")

    def test_item_just_past_the_boundary_is_fresh(self):
        item = build_item(self.user, EXPIRING_SOON_DAYS + 1)
        self.assertEqual(item.status, "fresh")


class FoodItemValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("tester", password="pass12345")

    def test_expiry_before_purchase_is_rejected(self):
        item = build_item(
            self.user,
            0,
            purchase_date=FIXED_TODAY,
            expiry_date=FIXED_TODAY - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn("expiry_date", context.exception.message_dict)

    def test_expiry_on_purchase_day_is_allowed(self):
        item = build_item(
            self.user, 0, purchase_date=FIXED_TODAY, expiry_date=FIXED_TODAY
        )
        item.full_clean()  # raises an error only if something is wrong

    def test_zero_quantity_is_rejected(self):
        item = build_item(self.user, 5, quantity=Decimal("0"))
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn("quantity", context.exception.message_dict)