from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.suggest, name="suggest"),
]