from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import build_analytics


@login_required
def analytics_dashboard(request):
    data = build_analytics(request.user)
    return render(request, "analytics/dashboard.html", {"data": data})