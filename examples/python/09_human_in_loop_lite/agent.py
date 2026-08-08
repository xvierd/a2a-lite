"""
Human-in-the-Loop Agent - A2A Lite Implementation

Demonstrates agents that pause for human confirmation before running
sensitive operations.

A2A Lite has no mid-execution question API, so this example uses the
standard two-phase pattern over the A2A protocol:

  1. Call the skill -> it validates the request and returns
     {"status": "confirmation_required", ...details...}.
  2. The human reviews and calls the same skill with confirmed=True
     -> the operation executes.

Run:  python agent.py
"""

import uuid
from a2a_lite import Agent

agent = Agent(
    name="HumanLoopAgent",
    description="Agent that asks for human confirmation before sensitive operations",
    version="1.0.0",
)


def _pending(action: str, details: dict) -> dict:
    """Build a confirmation-required response."""
    return {
        "status": "confirmation_required",
        "action": action,
        "details": details,
        "message": (
            f"Please review and call '{action}' again with confirmed=true "
            "to proceed."
        ),
    }


@agent.skill("purchase")
async def purchase(item: str, price: float, confirmed: bool = False) -> dict:
    """
    Purchase an item - requires human confirmation.

    Phase 1 (confirmed=False): returns the order details for review.
    Phase 2 (confirmed=True): executes the purchase.
    """
    if not confirmed:
        return _pending("purchase", {"item": item, "price": price})

    order_id = str(uuid.uuid4())[:8]
    return {
        "status": "completed",
        "order_id": order_id,
        "item": item,
        "price": price,
        "message": f"Purchase confirmed! Order ID: {order_id}",
    }


@agent.skill("delete_data")
async def delete_data(data_id: str, confirmed: bool = False) -> dict:
    """
    Delete data - irreversible, requires explicit confirmation.
    """
    if not confirmed:
        return _pending(
            "delete_data",
            {"data_id": data_id, "warning": "This action is IRREVERSIBLE"},
        )

    return {
        "status": "deleted",
        "data_id": data_id,
        "message": "Data permanently deleted",
    }


@agent.skill("approve_document")
async def approve_document(
    doc_id: str,
    decision: str | None = None,
    feedback: str | None = None,
) -> dict:
    """
    Document approval with multiple choices.

    Phase 1 (no decision): returns the available options.
    Phase 2 (decision set): applies approve / revise / reject.
    """
    if decision is None:
        return {
            "status": "decision_required",
            "doc_id": doc_id,
            "options": [
                {"decision": "approve", "label": "Approve - ready for publication"},
                {"decision": "revise", "label": "Request revision (pass feedback)"},
                {"decision": "reject", "label": "Reject (pass feedback as reason)"},
            ],
            "message": "Call again with decision='approve'|'revise'|'reject'.",
        }

    if decision == "approve":
        return {
            "status": "approved",
            "doc_id": doc_id,
            "message": "Document approved for publication",
        }
    if decision == "revise":
        return {
            "status": "revision_requested",
            "doc_id": doc_id,
            "feedback": feedback,
            "message": "Revision requested with feedback",
        }
    if decision == "reject":
        return {
            "status": "rejected",
            "doc_id": doc_id,
            "reason": feedback,
            "message": "Document rejected",
        }
    return {"status": "error", "message": f"Unknown decision: {decision}"}


@agent.skill("transfer_funds")
async def transfer_funds(
    amount: float,
    to_account: str,
    confirmed: bool = False,
) -> dict:
    """
    Transfer funds - requires confirmation with full cost breakdown.
    """
    if not confirmed:
        return _pending(
            "transfer_funds",
            {
                "amount": amount,
                "to_account": to_account,
                "fee": round(amount * 0.01, 2),
                "total": round(amount * 1.01, 2),
            },
        )

    transfer_id = str(uuid.uuid4())[:8]
    return {
        "status": "transferred",
        "transfer_id": transfer_id,
        "amount": amount,
        "to": to_account,
        "message": f"Transfer completed. ID: {transfer_id}",
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Human-in-the-Loop Agent - A2A Lite")
    print("=" * 70)
    print("Port: 8793")
    print("-" * 70)
    print("Skills demonstrating the two-phase confirmation pattern:")
    print("  - purchase:         Confirmation before purchase")
    print("  - delete_data:      Confirmation with irreversibility warning")
    print("  - approve_document: Multiple-choice approval flow")
    print("  - transfer_funds:   Confirmation with cost breakdown")
    print("-" * 70)
    print("Pattern: call once -> 'confirmation_required',")
    print("         call again with confirmed=true -> executes.")
    print("=" * 70)

    agent.run(port=8793)
