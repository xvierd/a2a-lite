"""
Human-in-the-Loop Agent - A2A Lite Implementation

Demonstrates agents that pause for human input using InteractionContext.
Essential for sensitive operations requiring confirmation.
"""

import uuid
from a2a_lite import Agent, InteractionContext

agent = Agent(
    name="HumanLoopAgent",
    description="Agent that asks for human confirmation when needed",
    version="1.0.0",
    task_store="memory"  # Required for persisting state during waits
)


@agent.skill("purchase")
async def purchase(item: str, price: float, ctx: InteractionContext = None) -> dict:
    """
    Purchase an item - requires human confirmation.
    
    The InteractionContext is auto-injected by A2A Lite.
    It allows asking questions mid-execution.
    """
    # Ask for confirmation
    confirmation = await ctx.confirm(
        f"Confirm purchase of {item} for ${price}?",
        default=False
    )
    
    if not confirmation:
        return {
            "status": "cancelled",
            "message": f"Purchase of {item} was cancelled by user"
        }
    
    # Process purchase
    order_id = str(uuid.uuid4())[:8]
    
    return {
        "status": "completed",
        "order_id": order_id,
        "item": item,
        "price": price,
        "message": f"Purchase confirmed! Order ID: {order_id}"
    }


@agent.skill("delete_data")
async def delete_data(data_id: str, ctx: InteractionContext = None) -> dict:
    """
    Delete data with multiple confirmations.
    
    Demonstrates multiple questions in sequence.
    """
    # First confirmation
    confirm1 = await ctx.confirm(
        f"Are you sure you want to delete data {data_id}?",
        default=False
    )
    
    if not confirm1:
        return {"status": "cancelled", "reason": "First confirmation denied"}
    
    # Second confirmation (sensitive operation)
    confirm2 = await ctx.confirm(
        "This action is IRREVERSIBLE. Type 'DELETE' to confirm:",
        default=False
    )
    
    if not confirm2:
        return {"status": "cancelled", "reason": "Second confirmation denied"}
    
    return {
        "status": "deleted",
        "data_id": data_id,
        "message": "Data permanently deleted"
    }


@agent.skill("approve_document")
async def approve_document(doc_id: str, ctx: InteractionContext = None) -> dict:
    """
    Document approval with multiple choice.
    
    Demonstrates choose() for multiple options.
    """
    # Present options
    choice = await ctx.choose(
        f"Review document {doc_id}. What is your decision?",
        options=[
            ("approve", "✓ Approve - Ready for publication"),
            ("revise", "✎ Request Revision - Needs changes"),
            ("reject", "✗ Reject - Not suitable")
        ]
    )
    
    if choice == "revise":
        # Ask for specific feedback
        feedback = await ctx.ask("What changes are needed?")
        
        return {
            "status": "revision_requested",
            "doc_id": doc_id,
            "feedback": feedback,
            "message": "Revision requested with feedback"
        }
    
    elif choice == "approve":
        return {
            "status": "approved",
            "doc_id": doc_id,
            "approved_at": "2024-01-01T10:00:00Z",
            "message": "Document approved for publication"
        }
    
    else:  # reject
        reason = await ctx.ask("Reason for rejection?")
        return {
            "status": "rejected",
            "doc_id": doc_id,
            "reason": reason,
            "message": "Document rejected"
        }


@agent.skill("transfer_funds")
async def transfer_funds(
    amount: float,
    to_account: str,
    ctx: InteractionContext = None
) -> dict:
    """
    Transfer funds - requires explicit confirmation with details.
    """
    # Build confirmation details
    details = f"""
Transfer Details:
  Amount: ${amount:,.2f}
  To: {to_account}
  Fee: ${amount * 0.01:,.2f}
  Total: ${amount * 1.01:,.2f}

Do you confirm this transfer?
"""
    
    confirmed = await ctx.confirm(details.strip(), default=False)
    
    if confirmed:
        transfer_id = str(uuid.uuid4())[:8]
        return {
            "status": "transferred",
            "transfer_id": transfer_id,
            "amount": amount,
            "to": to_account,
            "message": f"Transfer completed. ID: {transfer_id}"
        }
    
    return {
        "status": "cancelled",
        "message": "Transfer cancelled by user"
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Human-in-the-Loop Agent - A2A Lite")
    print("=" * 70)
    print("Port: 8793")
    print("-" * 70)
    print("Skills demonstrating human interaction:")
    print("  - purchase: Confirmation before purchase")
    print("  - delete_data: Multiple confirmations")
    print("  - approve_document: Multiple choice approval")
    print("  - transfer_funds: Detailed confirmation")
    print("-" * 70)
    print("A2A Lite handles:")
    print("  ✓ Task state persistence during waits")
    print("  ✓ Automatic task resumption")
    print("  ✓ Context preservation")
    print("  ✓ Question formatting (confirm/ask/choose)")
    print("=" * 70)
    
    agent.run(port=8793)
