from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from assistant.client import AIServiceError
from assistant.usage import UsageLimitExceeded, check_and_record

from .insights import MIN_RECORDS, generate_waste_insight
from .services import build_analytics


@login_required
def analytics_dashboard(request):
    data = build_analytics(request.user)
    return render(
        request,
        "analytics/dashboard.html",
        {
            "data": data,
            "insight": request.session.get("waste_insight"),
            "min_records": MIN_RECORDS,
        },
    )


@login_required
@require_POST
def generate_insight(request):
    data = build_analytics(request.user)

    if data is None or data["stats"]["total_count"] < MIN_RECORDS:
        messages.error(
            request,
            f"Record at least {MIN_RECORDS} items as consumed or wasted "
            "before generating insights.",
        )
        return redirect("analytics:dashboard")

    try:
        usage = check_and_record(request.user, "insights")
    except UsageLimitExceeded as exc:
        messages.error(request, str(exc))
        return redirect("analytics:dashboard")

    try:
        result = generate_waste_insight(data)
    except AIServiceError as exc:
        usage.delete()  # failed requests do not count against the limit
        messages.error(request, str(exc))
        return redirect("analytics:dashboard")

    request.session["waste_insight"] = {
        **result.model_dump(),
        "generated_at": timezone.localtime().strftime("%d %b %Y, %I:%M %p"),
    }
    messages.success(request, "Your insights are ready.")
    return redirect("analytics:dashboard")