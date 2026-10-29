import pandas as pd
from django.utils import timezone

from inventory.models import FoodItem, FoodLog

TREND_DAYS = 30


def build_analytics(user):
    """Turn a user's food logs into statistics and chart data using Pandas.

    Returns None when the user has no records yet.
    """
    rows = list(
        FoodLog.objects.filter(owner=user).values(
            "item_name",
            "category",
            "action",
            "quantity",
            "reason",
            "estimated_cost",
            "logged_on",
        )
    )
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["estimated_cost"] = df["estimated_cost"].astype(float)
    df["logged_on"] = pd.to_datetime(df["logged_on"])

    category_labels = dict(FoodItem.Category.choices)
    reason_labels = dict(FoodLog.Reason.choices)

    wasted = df[df["action"] == FoodLog.Action.WASTED]
    total_count = len(df)
    wasted_count = len(wasted)
    consumed_count = total_count - wasted_count

    # Waste by category (money) and by reason (number of times)
    by_category = (
        wasted.groupby("category")["estimated_cost"].sum().sort_values(ascending=False)
    )
    by_reason = wasted["reason"].value_counts()

    # Headline statistics
    top_item_name = None
    top_item_cost = 0.0
    top_reason = None
    top_reason_count = 0
    average_cost = 0.0

    if wasted_count:
        by_item = (
            wasted.groupby("item_name")
            .agg(cost=("estimated_cost", "sum"), times=("estimated_cost", "size"))
            .sort_values(["cost", "times"], ascending=False)
        )
        top_item_name = by_item.index[0]
        top_item_cost = round(float(by_item.iloc[0]["cost"]), 2)

        top_reason_key = by_reason.index[0]
        top_reason = reason_labels.get(top_reason_key, top_reason_key)
        top_reason_count = int(by_reason.iloc[0])

        average_cost = round(float(wasted["estimated_cost"].mean()), 2)

    stats = {
        "total_count": total_count,
        "wasted_count": wasted_count,
        "consumed_count": consumed_count,
        "waste_rate": round(wasted_count / total_count * 100, 1),
        "total_wasted_cost": round(float(wasted["estimated_cost"].sum()), 2),
        "average_cost": average_cost,
        "top_item_name": top_item_name,
        "top_item_cost": top_item_cost,
        "top_reason": top_reason,
        "top_reason_count": top_reason_count,
    }

    # Daily money wasted over the last TREND_DAYS days (days with no waste = 0)
    today = pd.Timestamp(timezone.localdate())
    start = today - pd.Timedelta(days=TREND_DAYS - 1)
    all_days = pd.date_range(start, today, freq="D")
    recent = wasted[wasted["logged_on"] >= start]
    daily = recent.groupby("logged_on")["estimated_cost"].sum()
    daily = daily.reindex(all_days, fill_value=0.0)

    charts = {
        "action": {
            "labels": ["Consumed", "Wasted"],
            "values": [consumed_count, wasted_count],
        },
        "category": {
            "labels": [category_labels.get(c, c) for c in by_category.index],
            "values": [round(float(v), 2) for v in by_category.values],
        },
        "reason": {
            "labels": [reason_labels.get(r, r) for r in by_reason.index],
            "values": [int(v) for v in by_reason.values],
        },
        "trend": {
            "labels": [day.strftime("%d %b") for day in daily.index],
            "values": [round(float(v), 2) for v in daily.values],
        },
    }

    return {"stats": stats, "charts": charts}