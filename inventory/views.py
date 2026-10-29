from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import FoodItemForm
from .models import FoodItem


@login_required
def item_list(request):
    items = FoodItem.objects.filter(owner=request.user)
    return render(request, "inventory/item_list.html", {"items": items})


@login_required
def item_create(request):
    if request.method == "POST":
        form = FoodItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.owner = request.user
            item.save()
            messages.success(request, f"{item.name} was added to your inventory.")
            return redirect("inventory:list")
    else:
        form = FoodItemForm()
    return render(
        request,
        "inventory/item_form.html",
        {"form": form, "title": "Add food item"},
    )


@login_required
def item_update(request, pk):
    item = get_object_or_404(FoodItem, pk=pk, owner=request.user)
    if request.method == "POST":
        form = FoodItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"{item.name} was updated.")
            return redirect("inventory:list")
    else:
        form = FoodItemForm(instance=item)
    return render(
        request,
        "inventory/item_form.html",
        {"form": form, "title": f"Edit {item.name}"},
    )


@login_required
def item_delete(request, pk):
    item = get_object_or_404(FoodItem, pk=pk, owner=request.user)
    if request.method == "POST":
        name = item.name
        item.delete()
        messages.success(request, f"{name} was deleted.")
        return redirect("inventory:list")
    return render(request, "inventory/item_confirm_delete.html", {"item": item})