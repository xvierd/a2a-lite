"""
Test client for the Hello World A2A Agent (A2A protocol v1.0).

This script demonstrates how to interact with an A2A v1.0 agent using
HTTP requests: well-known agent card + JSON-RPC SendMessage.

Usage:
    1. Start the server: python main.py
    2. Run this client: python test_client.py
"""

import json
import sys
import uuid

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx


AGENT_URL = "http://localhost:8787"
AGENT_CARD_URL = f"{AGENT_URL}/.well-known/agent-card.json"

# v1.0: every request must carry the protocol version header
V1_HEADERS = {"A2A-Version": "1.0"}


def get_agent_card():
    """Fetch and display the agent card."""
    print("=" * 70)
    print("Fetching Agent Card...")
    print("=" * 70)

    response = httpx.get(AGENT_CARD_URL)
    response.raise_for_status()

    card = response.json()
    print(f"\n🤖 Agent: {card['name']}")
    print(f"📝 Description: {card['description']}")
    print(f"🔖 Version: {card['version']}")
    print(f"\n🌐 Supported Interfaces:")
    for iface in card.get("supportedInterfaces", []):
        print(f"   - {iface['protocolBinding']} ({iface['protocolVersion']}): {iface['url']}")
    print(f"\n🎯 Skills:")
    for skill in card.get('skills', []):
        print(f"   - {skill['name']}: {skill['description']}")
    print(f"\n⚡ Capabilities:")
    caps = card.get('capabilities', {})
    print(f"   - Streaming: {caps.get('streaming', False)}")
    print(f"   - Push Notifications: {caps.get('pushNotifications', False)}")

    return card


def send_message(text: str) -> dict:
    """Send a message to the agent via JSON-RPC SendMessage and return the response."""
    request_id = str(uuid.uuid4())[:8]

    # v1.0 wire format: method "SendMessage", role "ROLE_USER", parts {"text": ...}
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "messageId": str(uuid.uuid4()),
                "parts": [
                    {
                        "text": text
                    }
                ]
            }
        }
    }

    print(f"\n📤 Sending message (ID: {request_id}):")
    print(f"   Text: '{text}'")

    response = httpx.post(AGENT_URL, json=payload, headers=V1_HEADERS, timeout=30.0)
    response.raise_for_status()

    return response.json()


def display_response(response: dict):
    """Display the agent's response."""
    print(f"\n📥 Received response:")

    if "error" in response:
        print(f"   ❌ Error: {response['error']}")
        return

    # v1.0: non-streaming replies come back as {"result": {"message": {...}}}
    message = response.get("result", {}).get("message", {})

    for part in message.get("parts", []):
        if "text" in part:
            print(f"\n   🤖 Agent says: {part['text']}")


def main():
    """Run the test client."""
    print("\n" + "=" * 70)
    print("  A2A Hello World - Test Client (v1.0)")
    print("=" * 70)

    try:
        # Step 1: Get agent card
        get_agent_card()

        # Step 2: Send test messages
        print("\n" + "=" * 70)
        print("Testing Agent Responses")
        print("=" * 70)

        # Test 1: Simple greeting
        response = send_message("Hello, A2A!")
        display_response(response)

        # Test 2: Another message
        print("\n" + "-" * 70)
        response = send_message("How does this protocol work?")
        display_response(response)

        # Test 3: Empty message (tests edge case)
        print("\n" + "-" * 70)
        response = send_message("")
        display_response(response)

        print("\n" + "=" * 70)
        print("✅ All tests completed successfully!")
        print("=" * 70)

    except httpx.ConnectError as e:
        print(f"\n❌ Connection Error: {e}")
        print(f"\nMake sure the server is running:")
        print(f"   python main.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
