from django.conf import settings
from django.db import models


class AIUsage(models.Model):
    """One row per AI request, used to enforce fair-use limits."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_usages",
    )
    feature = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI usage"
        verbose_name_plural = "AI usage"

    def __str__(self):
        return f"{self.feature} by {self.user} at {self.created_at:%Y-%m-%d %H:%M}"