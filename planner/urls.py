from django.urls import path

from . import views

app_name = "planner"

urlpatterns = [
    path("", views.week, name="week"),
    path("add/", views.entry_create, name="add"),
    path("add-recipe/", views.recipe_add, name="add_recipe"),
    path("<int:pk>/", views.entry_detail, name="detail"),
    path("<int:pk>/delete/", views.entry_delete, name="delete"),
]