"""
Test client for the Secure A2A Agent (A2A protocol v1.0).

Demonstrates authenticated requests against the agent:
API Key (header/query), Bearer token, and RBAC (admin permission).

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


AGENT_URL = "http://localhost:8790"
AGENT_CARD_URL = f"{AGENT_URL}/.well-known/agent-card.json"

V1_HEADERS = {"A2A-Version": "1.0"}


def send_message(text: str, extra_headers: dict | None = None, query: str = "") -> dict:
    """Send a message via JSON-RPC SendMessage with optional auth headers."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4())[:8],
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "messageId": str(uuid.uuid4()),
                "parts": [{"text": text}],
            }
        },
    }
    headers = {**V1_HEADERS, **(extra_headers or {})}
    response = httpx.post(f"{AGENT_URL}/{query}", json=payload, headers=headers, timeout=30.0)
    response.raise_for_status()
    return response.json()


def parse_payload(response: dict) -> dict:
    """Extract the JSON payload from the agent's response message."""
    if "error" in response:
        return {"error": response["error"]}
    message = response.get("result", {}).get("message", {})
    for part in message.get("parts", []):
        if "text" in part:
            return json.loads(part["text"])
    return {}


def show(title: str, payload: dict):
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print(f"{'-' * 70}")
    print(json.dumps(payload, indent=2))


def main():
    print("=" * 70)
    print("  A2A Secure Agent - Test Client (v1.0)")
    print("=" * 70)

    try:
        # Agent card (public)
        card = httpx.get(AGENT_CARD_URL).json()
        print(f"\n🤖 Agent: {card['name']} (v{card['version']})")
        print(f"   Security schemes: {list(card.get('securitySchemes', {}).keys())}")

        # 1. No credentials -> AuthenticationError
        show(
            "1. get_secret WITHOUT credentials (expect AuthenticationError)",
            parse_payload(send_message("get_secret")),
        )

        # 2. API Key header -> success
        show(
            "2. get_secret with X-API-Key header",
            parse_payload(send_message("get_secret", {"X-API-Key": "secret-key-123"})),
        )

        # 3. API Key query param -> success
        show(
            "3. get_user_info with ?api_key= query param",
            parse_payload(send_message("get_user_info", query="?api_key=client-key-456")),
        )

        # 4. Bearer token -> success
        show(
            "4. get_user_info with Bearer token",
            parse_payload(send_message("get_user_info", {"Authorization": "Bearer valid-token-abc"})),
        )

        # 5. admin_only with non-admin -> AuthorizationError
        show(
            "5. admin_only with non-admin key (expect AuthorizationError)",
            parse_payload(send_message("admin_only", {"X-API-Key": "secret-key-123"})),
        )

        # 6. admin_only with admin token -> success
        show(
            "6. admin_only with admin Bearer token",
            parse_payload(send_message("admin_only", {"Authorization": "Bearer admin-token-ghi"})),
        )

        # 7. public_info without credentials -> works
        show(
            "7. public_info WITHOUT credentials (public skill)",
            parse_payload(send_message("public_info")),
        )

        print("\n" + "=" * 70)
        print("✅ All auth scenarios completed!")
        print("=" * 70)

    except httpx.ConnectError as e:
        print(f"\n❌ Connection Error: {e}")
        print("\nMake sure the server is running: python main.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
