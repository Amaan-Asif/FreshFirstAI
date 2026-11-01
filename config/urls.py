from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("inventory/", include("inventory.urls")),
    path("analytics/", include("analytics.urls")),
    path("recipes/", include("recipes.urls")),
    path("planner/", include("planner.urls")),
    path("shopping/", include("shopping.urls")),
    path("", include("core.urls")),
]