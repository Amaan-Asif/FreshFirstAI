from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import FoodItemForm, FoodLogForm
from .models import FoodItem, FoodLog


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


@login_required
def log_item(request, pk):
    item = get_object_or_404(FoodItem, pk=pk, owner=request.user)

    if request.method == "POST":
        form = FoodLogForm(request.POST, item=item)
        if form.is_valid():
            with transaction.atomic():
                log = form.save(commit=False)
                log.owner = request.user
                log.food_item = item
                log.item_name = item.name
                log.category = item.category
                log.unit = item.unit
                log.save()

                remaining = item.quantity - log.quantity
                if remaining > 0:
                    item.quantity = remaining
                    item.save()
                    note = "The remaining amount stays in your inventory."
                else:
                    item.delete()
                    note = f"{log.item_name} was used up and removed from your inventory."

            messages.success(
                request,
                f"Recorded: {log.get_action_display().lower()} "
                f"{log.quantity.normalize():f} {log.unit} of {log.item_name}. {note}",
            )
            return redirect("inventory:list")
    else:
        form = FoodLogForm(item=item, initial={"quantity": item.quantity})

    return render(request, "inventory/log_form.html", {"form": form, "item": item})


@login_required
def log_list(request):
    logs = FoodLog.objects.filter(owner=request.user)
    wasted = logs.filter(action=FoodLog.Action.WASTED)

    context = {
        "logs": logs,
        "consumed_count": logs.filter(action=FoodLog.Action.CONSUMED).count(),
        "wasted_count": wasted.count(),
        "wasted_cost": wasted.aggregate(total=Sum("estimated_cost"))["total"]
        or Decimal("0.00"),
    }
    return render(request, "inventory/log_list.html", context)