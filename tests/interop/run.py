#!/usr/bin/env python3
"""Run real Lite clients against each language server; no LLM or external receiver.

Install package development dependencies and run Java's writeInteropClasspath first.
This harness deliberately fails if a selected runtime or fixture is unavailable.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "interop-secret"  # Public, disposable fixture credentials.
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def source_state():
    return {
        "gitCommit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "trackedWorktreeDirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=ROOT,
                text=True,
            )
        ),
    }


def require(condition, description):
    if not condition:
        raise AssertionError(description)


def fixture(language, args):
    if language == "python":
        python = os.environ.get(
            "A2ALITE_TEST_PYTHON", str(ROOT / "packages/python/.venv/bin/python")
        )
        return [python, str(ROOT / "packages/python/tests/interop_fixture.py"), *args]
    if language == "typescript":
        return [
            "node",
            str(ROOT / "packages/typescript/node_modules/tsx/dist/cli.mjs"),
            str(ROOT / "packages/typescript/tests/interop-fixture.ts"),
            *args,
        ]
    cp = ROOT / "packages/java/build/interop-classpath.txt"
    if not cp.exists():
        raise RuntimeError("Run packages/java/gradlew writeInteropClasspath first")
    java = (
        str(Path(os.environ["JAVA_HOME"]) / "bin/java")
        if os.environ.get("JAVA_HOME")
        else "java"
    )
    return [java, "-cp", cp.read_text().strip(), "com.a2alite.InteropFixture", *args]


def request(url, body=None, token=TOKEN):
    headers = {"A2A-Version": "1.0", "Content-Type": "application/json"}
    if token is not None:
        headers["X-API-Key"] = token
    req = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(), headers=headers
    )
    try:
        with HTTP.open(req, timeout=20) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode()


def rpc(url, method, params, token=TOKEN):
    identity = uuid4().hex
    status, headers, data = request(
        url,
        {"jsonrpc": "2.0", "id": identity, "method": method, "params": params},
        token,
    )
    require(status == 200, f"{method}: HTTP {status}: {data}")
    result = json.loads(data)
    require(
        result.get("id") == identity, f"{method}: JSON-RPC id not preserved: {result}"
    )
    return result


def message(skill, params=None):
    return {
        "message": {
            "messageId": uuid4().hex,
            "role": "ROLE_USER",
            "parts": [
                {"text": json.dumps({"skill": skill, "params": params or {}})},
            ],
        }
    }


def texts(value):
    """Collect text parts without double-counting the same Task's history."""
    return [part["text"] for part in value.get("parts", []) if "text" in part]


def protocol_checks(url):
    status, _, body = request(url + "/.well-known/agent-card.json")
    require(status == 200, "Agent card unavailable")
    card = json.loads(body)
    require(
        any(
            i.get("protocolVersion") == "1.0" and i.get("protocolBinding") == "JSONRPC"
            for i in card.get("supportedInterfaces", [])
        ),
        "Missing compatible JSONRPC interface",
    )
    status, _, _ = request(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": message("greet", {"text": "hello"}),
        },
        None,
    )
    require(status == 401, "Anonymous request must receive HTTP 401")
    task_response = rpc(url, "SendMessage", message("taskProbe"))
    task = task_response.get("result", {}).get("task", {})
    task_id = task.get("id")
    require(task_id, f"Explicit task did not return a Task: {task_response}")
    require(task["status"]["state"] == "TASK_STATE_COMPLETED", "Task did not complete")
    read = rpc(url, "GetTask", {"id": task_id}, "interop-rotated")
    require(
        read.get("result", {}).get("id") == task_id, "Credential rotation orphaned task"
    )
    for method in ("GetTask", "CancelTask"):
        require(
            "error" in rpc(url, method, {"id": task_id}, "interop-other"),
            f"Cross-user {method} allowed",
        )
    listing = rpc(url, "ListTasks", {"pageSize": 100}, "interop-other")
    require("error" not in listing, f"ListTasks failed: {listing}")
    require(task_id not in json.dumps(listing), "Cross-user ListTasks exposed task")

    # A completed Task emits no more events. CRUD here never sends an HTTP callback.
    for config_id in ("contract-one", "contract-two"):
        config = {
            "taskId": task_id,
            "id": config_id,
            "url": "https://8.8.8.8/a2alite-interop",
        }
        created = rpc(url, "CreateTaskPushNotificationConfig", config)
        require(
            created.get("result", {}).get("id") == config_id,
            f"Callback config ID lost: {created}",
        )
    configs = rpc(url, "ListTaskPushNotificationConfigs", {"taskId": task_id})
    require(
        "contract-one" in json.dumps(configs) and "contract-two" in json.dumps(configs),
        "Callback configurations were overwritten",
    )
    require(
        "error"
        in rpc(
            url,
            "GetTaskPushNotificationConfig",
            {"taskId": task_id, "id": "contract-one"},
            "interop-other",
        ),
        "Cross-user callback read allowed",
    )
    for config_id in ("contract-one", "contract-two"):
        require(
            "error"
            not in rpc(
                url,
                "DeleteTaskPushNotificationConfig",
                {"taskId": task_id, "id": config_id},
            ),
            "Callback deletion failed",
        )

    identity = uuid4().hex
    status, headers, stream = request(
        url,
        {
            "jsonrpc": "2.0",
            "id": identity,
            "method": "SendStreamingMessage",
            "params": message("stream"),
        },
    )
    require(
        status == 200 and "text/event-stream" in headers.get("Content-Type", ""),
        "Invalid SSE response media type",
    )
    events = [
        json.loads(line[5:].strip())
        for line in stream.splitlines()
        if line.startswith("data:") and line[5:].strip()
    ]
    require(
        events and events[0].get("result", {}).get("task", {}).get("id"),
        "SSE must start with a Task snapshot",
    )
    require(all(e.get("id") == identity for e in events), "SSE JSON-RPC IDs were lost")
    require("TASK_STATE_COMPLETED" in stream, "SSE did not reach completion")
    failure = rpc(url, "SendMessage", message("fail"))
    require(
        "error" in failure or "TASK_STATE_FAILED" in json.dumps(failure),
        "Failed skill reported success",
    )
    return {
        "discovery": True,
        "anonymousDenied": True,
        "rotation": True,
        "ownerIsolation": True,
        "pushConfigIds": True,
        "initialSseTask": True,
        "failure": True,
    }


@contextlib.contextmanager
def server(language, log_dir, extra_env=None):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    logfile = Path(log_dir) / f"{language}-{uuid4().hex[:8]}.log"
    env = dict(
        os.environ, PYTHONPATH=str(ROOT / "packages/python/src"), PYTHONUNBUFFERED="1"
    )
    env.update(extra_env or {})
    with logfile.open("w+") as log:
        proc = subprocess.Popen(
            fixture(language, ["server", "--port", str(port)]),
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 30
            url = f"http://127.0.0.1:{port}"
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"{language} server exited: {logfile.read_text()[-6000:]}"
                    )
                try:
                    status, _, _ = request(url + "/.well-known/agent-card.json")
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            else:
                raise TimeoutError(
                    f"{language} startup timed out: {logfile.read_text()[-6000:]}"
                )
            yield LocalServer(url, proc, logfile)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)


@dataclass
class LocalServer:
    url: str
    process: subprocess.Popen
    logfile: Path

    def crash(self):
        """Kill only this fixture's process group, deliberately bypassing graceful cleanup."""
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)


def run_client(language, url):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "packages/python/src"))
    result = subprocess.run(
        fixture(language, ["client", "--url", url]),
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    require(
        result.returncode == 0,
        f"{language} client failed: {result.stdout[-4000:]}\n{result.stderr[-4000:]}",
    )
    records = [
        line.removeprefix("A2A_LITE_RESULT ")
        for line in result.stdout.splitlines()
        if line.startswith("A2A_LITE_RESULT ")
    ]
    require(
        len(records) == 1,
        f"{language} client must return one result: {result.stdout[-4000:]}",
    )
    record = json.loads(records[0])
    for name in ("message", "task", "taskRead", "stream"):
        require(record.get(name) is True, f"{language} did not prove {name}: {record}")
    return record


def official_client(url):
    python = os.environ.get(
        "A2ALITE_TEST_PYTHON", str(ROOT / "packages/python/.venv/bin/python")
    )
    result = subprocess.run(
        [python, str(Path(__file__).with_name("official_sdk.py")), "--url", url],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    require(
        result.returncode == 0,
        f"Official SDK client failed: {result.stdout[-2000:]}\n{result.stderr[-4000:]}",
    )
    records = [
        json.loads(line.removeprefix("A2A_LITE_OFFICIAL "))
        for line in result.stdout.splitlines()
        if line.startswith("A2A_LITE_OFFICIAL ")
    ]
    require(len(records) == 1, "Official SDK probe did not report its result")
    return records[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=("python", "typescript", "java"),
        default=["python", "typescript", "java"],
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-protocol",
        action="store_true",
        help="Diagnostic only: omit shared protocol probes",
    )
    args = parser.parse_args()
    report = {
        "schemaVersion": 1,
        **source_state(),
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "cpuCount": os.cpu_count(),
        "pairs": [],
        "protocol": [],
        "officialSdk": [],
        "success": False,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="a2alite-interop-") as logs:
            for server_language in args.languages:
                with server(server_language, logs) as runtime:
                    url = runtime.url
                    if not args.skip_protocol:
                        checks = protocol_checks(url)
                        report["protocol"].append({"server": server_language, **checks})
                        report["officialSdk"].append(
                            {"server": server_language, **official_client(url)}
                        )
                    for client_language in args.languages:
                        checks = run_client(client_language, url)
                        pair = {
                            "client": client_language,
                            "server": server_language,
                            **checks,
                        }
                        report["pairs"].append(pair)
                        print(json.dumps(pair), flush=True)
        report["success"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Passed {len(report['pairs'])} client/server pairings and {len(report['protocol'])} protocol profiles"
    )


if __name__ == "__main__":
    main()
