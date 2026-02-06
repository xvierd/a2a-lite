"""
Finance agent that categorizes expenses.

Run with: python examples/04_multi_agent/finance_agent.py
"""
from typing import List, Dict
from a2a_lite import Agent

agent = Agent(
    name="FinanceHelper",
    description="Categorizes and analyzes expenses",
)

CATEGORIES = {
    "food": ["restaurant", "coffee", "grocery", "uber eats", "delivery", "lunch", "dinner"],
    "transport": ["uber", "taxi", "gas", "parking", "subway", "lyft", "metro"],
    "entertainment": ["netflix", "spotify", "movie", "concert", "game", "hulu", "disney"],
    "utilities": ["electric", "water", "internet", "phone", "gas bill"],
    "shopping": ["amazon", "target", "walmart", "costco", "clothing"],
}


@agent.skill("categorize", description="Categorize a single expense")
async def categorize(description: str, amount: float) -> dict:
    """Categorize an expense based on its description."""
    description_lower = description.lower()

    for category, keywords in CATEGORIES.items():
        if any(kw in description_lower for kw in keywords):
            return {
                "description": description,
                "amount": amount,
                "category": category,
                "confidence": 0.9,
            }

    return {
        "description": description,
        "amount": amount,
        "category": "other",
        "confidence": 0.5,
    }


@agent.skill("bulk_categorize", description="Categorize multiple expenses")
async def bulk_categorize(expenses: List[Dict]) -> dict:
    """Categorize multiple expenses at once."""
    results = []
    for exp in expenses:
        result = await categorize(exp["description"], exp["amount"])
        results.append(result)

    # Calculate totals by category
    totals = {}
    for r in results:
        cat = r["category"]
        totals[cat] = totals.get(cat, 0) + r["amount"]

    return {
        "categorized": results,
        "totals": totals,
        "total_amount": sum(r["amount"] for r in results),
    }


@agent.skill("analyze_spending", description="Analyze spending patterns")
async def analyze_spending(expenses: List[Dict]) -> dict:
    """Analyze spending patterns from categorized expenses."""
    categorized = await bulk_categorize(expenses)

    totals = categorized["totals"]
    total = categorized["total_amount"]

    # Calculate percentages
    percentages = {
        cat: round((amt / total) * 100, 1) if total > 0 else 0
        for cat, amt in totals.items()
    }

    # Find highest spending category
    if totals:
        highest = max(totals.items(), key=lambda x: x[1])
        lowest = min(totals.items(), key=lambda x: x[1])
    else:
        highest = lowest = ("none", 0)

    return {
        "total_spending": total,
        "by_category": totals,
        "percentages": percentages,
        "highest_category": {"name": highest[0], "amount": highest[1]},
        "lowest_category": {"name": lowest[0], "amount": lowest[1]},
        "num_transactions": len(expenses),
    }


if __name__ == "__main__":
    agent.run(port=8787)
