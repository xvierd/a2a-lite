"""
Integration tests for Calculator Agent using Google A2A SDK (A2A v1.0).

These tests verify the A2A protocol v1.0 implementation works correctly:
well-known agent card, JSON-RPC SendMessage, task lifecycle.
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid

import httpx
import pytest

PORT = int(os.getenv("TEST_PORT", "18288"))
BASE_URL = f"http://localhost:{PORT}"

V1_HEADERS = {"A2A-Version": "1.0"}


@pytest.fixture(scope="module")
def server():
    """Start the server for testing."""
    env = {**os.environ, "PORT": str(PORT)}
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env,
    )
    time.sleep(3)  # Wait for server to start

    yield proc

    # Cleanup
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_agent_card(server):
    """Test agent card endpoint (v1.0 well-known path)."""
    response = httpx.get(f"{BASE_URL}/.well-known/agent-card.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "CalculatorAgent"
    assert data["version"] == "1.0.0"
    assert len(data["skills"]) == 5

    # v1.0: endpoints are declared in supportedInterfaces
    iface = data["supportedInterfaces"][0]
    assert iface["protocolBinding"] == "JSONRPC"
    assert iface["protocolVersion"] == "1.0"

    skill_ids = [s["id"] for s in data["skills"]]
    for expected in ["add", "subtract", "multiply", "divide", "power"]:
        assert expected in skill_ids


def send_task(skill: str, params: dict) -> dict:
    """Send a calculator request via JSON-RPC SendMessage (v1.0 wire)."""
    payload = {
        "jsonrpc": "2.0",
        "method": "SendMessage",
        "id": f"test-{uuid.uuid4().hex[:8]}",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "messageId": uuid.uuid4().hex,
                "parts": [{
                    "text": json.dumps({"skill": skill, "params": params})
                }],
            }
        }
    }

    response = httpx.post(
        f"{BASE_URL}/", json=payload, headers=V1_HEADERS, timeout=30.0
    )
    return response.json()


def _get_task(response: dict) -> dict:
    """Extract the task from a v1.0 SendMessage response."""
    assert "result" in response, f"Unexpected response: {response}"
    return response["result"]["task"]


def test_add(server):
    """Test addition skill."""
    task = _get_task(send_task("add", {"a": 10, "b": 5}))

    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    # Result is published as a data artifact
    artifacts = task["artifacts"]
    assert artifacts[0]["name"] == "result"
    assert artifacts[0]["parts"][0]["data"]["result"] == 15


def test_subtract(server):
    """Test subtraction skill."""
    task = _get_task(send_task("subtract", {"a": 10, "b": 3}))
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["artifacts"][0]["parts"][0]["data"]["result"] == 7


def test_multiply(server):
    """Test multiplication skill."""
    task = _get_task(send_task("multiply", {"a": 6, "b": 7}))
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["artifacts"][0]["parts"][0]["data"]["result"] == 42


def test_divide(server):
    """Test division skill."""
    task = _get_task(send_task("divide", {"a": 10, "b": 3}))
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    data = task["artifacts"][0]["parts"][0]["data"]
    assert abs(data["result"] - 3.333) < 0.01
    assert data["remainder"] == 1


def test_power(server):
    """Test power/exponentiation skill."""
    task = _get_task(send_task("power", {"base": 2, "exponent": 10}))
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["artifacts"][0]["parts"][0]["data"]["result"] == 1024


def test_divide_by_zero(server):
    """Test division by zero error handling -> failed task."""
    task = _get_task(send_task("divide", {"a": 10, "b": 0}))

    assert task["status"]["state"] == "TASK_STATE_FAILED"
    message_text = task["status"]["message"]["parts"][0]["text"]
    assert "Division by zero" in message_text


def test_unknown_skill(server):
    """Test unknown skill error -> failed task."""
    task = _get_task(send_task("unknown", {"a": 1}))
    assert task["status"]["state"] == "TASK_STATE_FAILED"


def test_invalid_json(server):
    """Test invalid JSON input -> failed task."""
    payload = {
        "jsonrpc": "2.0",
        "method": "SendMessage",
        "id": "test-invalid",
        "params": {
            "message": {
                "role": "ROLE_USER",
                "messageId": uuid.uuid4().hex,
                "parts": [{"text": "not valid json"}],
            }
        }
    }

    response = httpx.post(
        f"{BASE_URL}/", json=payload, headers=V1_HEADERS, timeout=30.0
    )
    task = _get_task(response.json())
    assert task["status"]["state"] == "TASK_STATE_FAILED"


def test_get_task(server):
    """Test GetTask for a previously created task."""
    task = _get_task(send_task("add", {"a": 1, "b": 2}))
    task_id = task["id"]

    payload = {
        "jsonrpc": "2.0",
        "method": "GetTask",
        "id": "test-get",
        "params": {"id": task_id}
    }

    response = httpx.post(
        f"{BASE_URL}/", json=payload, headers=V1_HEADERS, timeout=10.0
    )
    result = response.json()

    assert "result" in result
    # GetTask returns the task object directly in result
    assert result["result"]["id"] == task_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
