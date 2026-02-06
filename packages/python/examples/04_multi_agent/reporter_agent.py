"""
Reporter agent that calls Finance agent and generates reports.

Run with:
  1. First start the finance agent: python examples/04_multi_agent/finance_agent.py
  2. Then start this agent: python examples/04_multi_agent/reporter_agent.py
"""
import json
from typing import List, Dict
from a2a_lite import Agent

agent = Agent(
    name="ExpenseReporter",
    description="Generates expense reports using Finance agent",
)

FINANCE_AGENT_URL = "http://localhost:8787"


@agent.skill("generate_report", description="Generate expense report from raw expenses")
async def generate_report(expenses: List[Dict]) -> dict:
    """Generate a full expense report by calling the Finance agent."""
    # Call the Finance agent for analysis
    message = json.dumps({
        "skill": "analyze_spending",
        "params": {"expenses": expenses}
    })

    try:
        result = await agent.call_remote(FINANCE_AGENT_URL, message)

        # Extract the analysis from the response
        # The response structure depends on A2A SDK version
        analysis = result

        return {
            "report_type": "expense_summary",
            "generated_by": "ExpenseReporter",
            "data": analysis,
            "status": "success",
        }
    except Exception as e:
        return {
            "report_type": "expense_summary",
            "generated_by": "ExpenseReporter",
            "error": str(e),
            "status": "failed",
            "hint": "Make sure FinanceHelper is running on port 8787",
        }


@agent.skill("quick_summary", description="Get a quick spending summary")
async def quick_summary(expenses: List[Dict]) -> str:
    """Generate a human-readable summary."""
    report = await generate_report(expenses)

    if report["status"] == "failed":
        return f"Failed to generate report: {report.get('error', 'Unknown error')}"

    data = report.get("data", {})

    # Try to extract relevant info from the nested response
    total = data.get("total_spending", "unknown")
    num_tx = data.get("num_transactions", len(expenses))

    return f"Expense Summary: {num_tx} transactions totaling ${total}"


if __name__ == "__main__":
    # Run on a different port since finance_agent uses 8787
    agent.run(port=8788)
