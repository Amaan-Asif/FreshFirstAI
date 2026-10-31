from django.conf import settings
from django.utils import timezone

from .models import AIUsage


class UsageLimitExceeded(Exception):
    """Raised with a message that is safe to show to the user."""


def check_and_record(user, feature):
    """Enforce the limits, then record this request. Returns the new record."""
    now = timezone.now()
    start_of_day = timezone.localtime(now).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    today = AIUsage.objects.filter(created_at__gte=start_of_day)

    if today.count() >= settings.AI_GLOBAL_DAILY_LIMIT:
        raise UsageLimitExceeded(
            "The AI features have reached their daily limit for everyone. "
            "Please try again tomorrow."
        )

    mine = today.filter(user=user)

    if mine.count() >= settings.AI_DAILY_LIMIT_PER_USER:
        raise UsageLimitExceeded(
            f"You have used your {settings.AI_DAILY_LIMIT_PER_USER} AI requests "
            "for today. Please try again tomorrow."
        )

    last = mine.first()
    if last and (now - last.created_at).total_seconds() < settings.AI_COOLDOWN_SECONDS:
        raise UsageLimitExceeded(
            "Please wait a few seconds before making another AI request."
        )

    return AIUsage.objects.create(user=user, feature=feature)