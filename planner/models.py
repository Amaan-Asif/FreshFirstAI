from django.conf import settings
from django.db import models


class MealPlanEntry(models.Model):
    """One planned meal on one day.

    Recipe details (ingredients, steps) are copied in when a meal comes from an
    AI recipe, so the plan keeps working even if the suggestions change later.
    """

    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        DINNER = "dinner", "Dinner"
        SNACK = "snack", "Snack"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meal_plan_entries",
    )
    date = models.DateField()
    meal_type = models.CharField(
        max_length=10, choices=MealType.choices, default=MealType.DINNER
    )
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    # Filled in only when the meal comes from an AI recipe
    description = models.TextField(blank=True)
    cooking_time_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    servings = models.PositiveSmallIntegerField(null=True, blank=True)
    inventory_ingredients = models.JSONField(default=list, blank=True)
    extra_ingredients = models.JSONField(default=list, blank=True)
    steps = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]
        verbose_name_plural = "meal plan entries"
        indexes = [models.Index(fields=["owner", "date"])]

    def __str__(self):
        return f"{self.get_meal_type_display()} on {self.date}: {self.title}"