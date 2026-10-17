"""Stable principal and tenant boundaries, including external SDK stores."""

import base64
import json
from uuid import uuid4

from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore
from starlette.testclient import TestClient

from a2a_lite import Agent
from a2a_lite.auth import APIKeyAuth, AuthResult
from a2a_lite.server import AuthenticatedUser, LiteRequestHandler


def test_principal_encoding_preserves_legacy_and_separates_namespaces():
    assert AuthResult.success(" alice ").principal == " alice "
    values = [AuthResult.success("same", namespace="issuer-a"), AuthResult.success("same", namespace="issuer-b")]
    assert values[0].principal != values[1].principal
    assert json.loads(base64.urlsafe_b64decode(values[0].principal[7:] + "==")) == ["issuer-a", "same"]
    escaped = AuthResult.success(values[0].principal)
    assert escaped.principal not in {item.principal for item in values}


def test_authorization_uses_request_local_context():
    result = AuthResult.success("user", authorized_tenants={"a", "b"})
    context = ServerCallContext(user=AuthenticatedUser(result), state={"auth_result": result}, tenant="a")
    scoped = LiteRequestHandler._authorize(context)
    assert context.user.user_name == "user"
    assert scoped.user.user_name != "user"
    assert scoped.state["auth_result"].user_id == "user"


def test_key_rotation_and_tenant_isolation_with_external_sdk_store():
    agent = Agent(
        name="TenantAgent",
        description="Tenant-aware external store",
        protocol_task_store=InMemoryTaskStore(),
        auth=APIKeyAuth(
            principals={"old": "account", "new": "account"}, namespace="keys", authorized_tenants={"a", "b"}
        ),
    )

    @agent.skill("work", task=True)
    async def work(auth: AuthResult):
        return {"user": auth.user_id, "namespace": auth.namespace}

    with TestClient(agent.get_app()) as client:

        def rpc(method, params, tenant="a", key="new"):
            return client.post(
                "/",
                headers={"A2A-Version": "1.0", "X-API-Key": key},
                json={"jsonrpc": "2.0", "id": uuid4().hex, "method": method, "params": {**params, "tenant": tenant}},
            ).json()

        task = rpc(
            "SendMessage",
            {
                "message": {
                    "role": "ROLE_USER",
                    "messageId": uuid4().hex,
                    "parts": [{"text": '{"skill":"work","params":{}}'}],
                }
            },
            key="old",
        )["result"]["task"]
        assert json.loads(task["artifacts"][0]["parts"][0]["text"]) == {"user": "account", "namespace": "keys"}
        assert rpc("GetTask", {"id": task["id"]})["result"]["id"] == task["id"]
        for method in (
            "GetTask",
            "CancelTask",
            "SubscribeToTask",
            "CreateTaskPushNotificationConfig",
            "GetTaskPushNotificationConfig",
            "DeleteTaskPushNotificationConfig",
            "ListTaskPushNotificationConfigs",
        ):
            result = rpc(
                method, {"id": task["id"], "taskId": task["id"], "url": "https://callback.example/hook"}, tenant="b"
            )
            assert result["error"]["code"] == -32001, (method, result)
        assert not rpc("ListTasks", {}, tenant="b")["result"].get("tasks")
        assert "not authorized" in rpc("GetTask", {"id": task["id"]}, tenant="c")["error"]["message"]
        headers = {"A2A-Version": "1.0", "X-API-Key": "new"}
        assert client.get(f"/a/tasks/{task['id']}", headers=headers).status_code == 200
        assert client.get(f"/b/tasks/{task['id']}", headers=headers).status_code == 404


def test_no_auth_cannot_select_nondefault_tenant():
    agent = Agent(name="Public", description="Only default tenant")
    with TestClient(agent.get_app()) as client:
        response = client.get("/private/tasks", headers={"A2A-Version": "1.0"})
    assert response.status_code == 400
    assert "not authorized" in response.text


def test_shared_cross_language_identity_vectors():
    from pathlib import Path

    from a2a_lite.server import AuthenticatedUser

    vectors = json.loads((Path(__file__).resolve().parents[3] / "tests/contracts/identity.json").read_text())["vectors"]
    for vector in vectors:
        result = AuthResult.success(
            vector["userId"], namespace=vector["namespace"], authorized_tenants={vector["tenant"]}
        )
        assert result.principal == vector["principalKey"]
        assert AuthenticatedUser(result, vector["tenant"]).user_name == vector["ownerKey"]
