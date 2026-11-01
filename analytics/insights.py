import json

from pydantic import BaseModel

from assistant.client import AIServiceError, generate_json

MIN_RECORDS = 3


class WasteInsight(BaseModel):
    summary: str
    patterns: list[str]
    suggestions: list[str]


def build_insight_input(data):
    """Turn the analytics numbers into a small summary to send to the AI."""
    stats = data["stats"]
    charts = data["charts"]
    trend = charts["trend"]["values"]

    top_item = None
    if stats["top_item_name"]:
        top_item = {
            "name": stats["top_item_name"],
            "money_wasted_rupees": stats["top_item_cost"],
        }

    top_reason = None
    if stats["top_reason"]:
        top_reason = {
            "reason": stats["top_reason"],
            "times": stats["top_reason_count"],
        }

    return {
        "total_records": stats["total_count"],
        "consumed_records": stats["consumed_count"],
        "wasted_records": stats["wasted_count"],
        "waste_rate_percent": stats["waste_rate"],
        "total_money_wasted_rupees": stats["total_wasted_cost"],
        "average_cost_per_waste_rupees": stats["average_cost"],
        "most_wasted_item": top_item,
        "most_common_reason": top_reason,
        "money_wasted_by_category_rupees": dict(
            zip(charts["category"]["labels"], charts["category"]["values"])
        ),
        "times_wasted_by_reason": dict(
            zip(charts["reason"]["labels"], charts["reason"]["values"])
        ),
        "money_wasted_last_7_days_rupees": round(sum(trend[-7:]), 2),
        "money_wasted_previous_7_days_rupees": round(sum(trend[-14:-7]), 2),
    }


def build_prompt(summary):
    return f"""You are a friendly food-waste coach inside a household food management app.
Below are statistics about one person's recorded food consumption and waste. Money is in Indian rupees.

Write:
- summary: 2 to 3 sentences describing their overall food-waste situation.
- patterns: 2 to 4 short observations about patterns in the numbers, for example which category or reason causes the most waste, or whether waste is rising or falling.
- suggestions: 3 to 5 practical, specific tips to reduce their waste, based on those patterns.

Rules:
- Use only the numbers given. Do not invent figures, foods or events.
- If there is little data, say so briefly instead of guessing.
- Be encouraging and non-judgmental. Do not give medical or nutrition advice.
- Keep each pattern and each suggestion to one or two sentences.

Statistics (JSON):
{json.dumps(summary, ensure_ascii=False, indent=2)}
"""


def generate_waste_insight(data):
    summary = build_insight_input(data)
    result = generate_json(build_prompt(summary), WasteInsight)

    result.patterns = [text.strip() for text in result.patterns if text.strip()][:5]
    result.suggestions = [text.strip() for text in result.suggestions if text.strip()][:5]

    if not result.summary.strip() or not result.suggestions:
        raise AIServiceError(
            "The AI returned an incomplete answer. Please try again."
        )
    return result