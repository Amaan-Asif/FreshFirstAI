from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("inventory", views.FoodItemViewSet, basename="inventory")
router.register("logs", views.FoodLogViewSet, basename="logs")

app_name = "api"

urlpatterns = [
    path("analytics/summary/", views.AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("", include(router.urls)),
]