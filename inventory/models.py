from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

# Items expiring within this many days are flagged as "expiring soon".
EXPIRING_SOON_DAYS = 3


class FoodItem(models.Model):
    class Category(models.TextChoices):
        FRUITS = "fruits", "Fruits"
        VEGETABLES = "vegetables", "Vegetables"
        DAIRY = "dairy", "Dairy"
        MEAT_FISH = "meat_fish", "Meat and fish"
        GRAINS = "grains", "Grains and bread"
        PULSES = "pulses", "Pulses and lentils"
        SNACKS = "snacks", "Snacks"
        BEVERAGES = "beverages", "Beverages"
        FROZEN = "frozen", "Frozen food"
        SPICES = "spices", "Spices and sauces"
        OTHER = "other", "Other"

    class Unit(models.TextChoices):
        PIECES = "pcs", "pcs"
        KILOGRAMS = "kg", "kg"
        GRAMS = "g", "g"
        LITRES = "l", "litres"
        MILLILITRES = "ml", "ml"
        PACKS = "pack", "packs"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="food_items",
    )
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECES)
    purchase_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField()
    storage_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["expiry_date", "name"]

    def __str__(self):
        return f"{self.name} ({self.owner})"

    def clean(self):
        super().clean()
        if (
            self.purchase_date
            and self.expiry_date
            and self.expiry_date < self.purchase_date
        ):
            raise ValidationError(
                {"expiry_date": "Expiry date cannot be before the purchase date."}
            )

    @property
    def days_until_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    @property
    def status(self):
        days = self.days_until_expiry
        if days < 0:
            return "expired"
        if days <= EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "fresh"


class FoodLog(models.Model):
    """A record of food that was consumed or wasted.

    The item's name, category and unit are copied into the log so the
    history stays correct even after the inventory item is deleted.
    """

    class Action(models.TextChoices):
        CONSUMED = "consumed", "Consumed"
        WASTED = "wasted", "Wasted"

    class Reason(models.TextChoices):
        EXPIRED = "expired", "Expired before use"
        SPOILED = "spoiled", "Spoiled or went bad"
        TOO_MUCH = "too_much", "Bought or cooked too much"
        LEFTOVERS = "leftovers", "Leftovers not eaten"
        DISLIKED = "disliked", "Did not like it"
        OTHER = "other", "Other"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="food_logs",
    )
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    item_name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=FoodItem.Category.choices)
    unit = models.CharField(max_length=10, choices=FoodItem.Unit.choices)
    action = models.CharField(
        max_length=10, choices=Action.choices, default=Action.CONSUMED
    )
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.CharField(max_length=20, choices=Reason.choices, blank=True)
    estimated_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    logged_on = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-logged_on", "-id"]

    def __str__(self):
        return f"{self.get_action_display()} {self.quantity} {self.unit} {self.item_name}"