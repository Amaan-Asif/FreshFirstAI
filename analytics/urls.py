from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.analytics_dashboard, name="dashboard"),
    path("insights/", views.generate_insight, name="insights"),
]