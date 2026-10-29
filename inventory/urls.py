from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.item_list, name="list"),
    path("add/", views.item_create, name="add"),
    path("<int:pk>/edit/", views.item_update, name="edit"),
    path("<int:pk>/delete/", views.item_delete, name="delete"),
]