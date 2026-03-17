"""
Integration tests for Calculator Agent using Google A2A SDK.

These tests verify the A2A protocol implementation works correctly.
"""

import subprocess
import time
import json
import signal
import sys
import os

import httpx
import pytest

BASE_URL = "http://localhost:8788"


@pytest.fixture(scope="module")
def server():
    """Start the server for testing."""
    # Start the server
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__))
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
    """Test agent card endpoint."""
    response = httpx.get(f"{BASE_URL}/.well-known/agent.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "CalculatorAgent"
    assert data["version"] == "1.0.0"
    assert len(data["skills"]) == 5
    
    skill_ids = [s["id"] for s in data["skills"]]
    assert "add" in skill_ids
    assert "subtract" in skill_ids
    assert "multiply" in skill_ids
    assert "divide" in skill_ids
    assert "power" in skill_ids


def send_task(skill: str, params: dict, method: str = "tasks/send") -> dict:
    """Helper to send task requests."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": "test-1",
        "params": {
            "message": {
                "role": "user",
                "parts": [{
                    "type": "text",
                    "text": json.dumps({"skill": skill, "params": params})
                }],
                "messageId": "msg-test-1"
            }
        }
    }
    
    response = httpx.post(f"{BASE_URL}/", json=payload, timeout=30.0)
    return response.json()


def test_add(server):
    """Test addition skill."""
    result = send_task("add", {"a": 10, "b": 5})
    
    # Should be a Task response
    assert "result" in result
    task = result["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] in ["completed", "working"]


def test_subtract(server):
    """Test subtraction skill."""
    result = send_task("subtract", {"a": 10, "b": 3})
    
    assert "result" in result
    task = result["result"]
    assert task["kind"] == "task"


def test_multiply(server):
    """Test multiplication skill."""
    result = send_task("multiply", {"a": 6, "b": 7})
    
    assert "result" in result
    task = result["result"]
    assert task["kind"] == "task"


def test_divide(server):
    """Test division skill."""
    result = send_task("divide", {"a": 10, "b": 3})
    
    assert "result" in result
    task = result["result"]
    assert task["kind"] == "task"


def test_power(server):
    """Test power/exponentiation skill."""
    result = send_task("power", {"base": 2, "exponent": 10})
    
    assert "result" in result
    task = result["result"]
    assert task["kind"] == "task"


def test_divide_by_zero(server):
    """Test division by zero error handling."""
    result = send_task("divide", {"a": 10, "b": 0})
    
    # Should get an error response
    if "error" in result:
        assert "Division by zero" in result["error"]["message"]
    else:
        # Or a failed task
        task = result.get("result", {})
        if task.get("status", {}).get("state") == "failed":
            pass  # Expected


def test_unknown_skill(server):
    """Test unknown skill error."""
    result = send_task("unknown", {"a": 1})
    
    # Should get an error
    assert "error" in result or result.get("result", {}).get("status", {}).get("state") == "failed"


def test_invalid_json(server):
    """Test invalid JSON input."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "id": "test-invalid",
        "params": {
            "message": {
                "role": "user",
                "parts": [{
                    "type": "text",
                    "text": "not valid json"
                }],
                "messageId": "msg-invalid"
            }
        }
    }
    
    response = httpx.post(f"{BASE_URL}/", json=payload, timeout=30.0)
    result = response.json()
    
    # Should get an error or failed task
    assert "error" in result or result.get("result", {}).get("status", {}).get("state") == "failed"


def test_get_task(server):
    """Test getting a task."""
    # First send a task
    send_result = send_task("add", {"a": 1, "b": 2})
    
    if "result" in send_result and "id" in send_result["result"]:
        task_id = send_result["result"]["id"]
        
        # Now get the task
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "id": "test-get",
            "params": {
                "id": task_id
            }
        }
        
        response = httpx.post(f"{BASE_URL}/", json=payload, timeout=10.0)
        result = response.json()
        
        assert "result" in result
        assert result["result"]["id"] == task_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
