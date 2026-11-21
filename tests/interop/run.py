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
INTEROP = Path(__file__).resolve().parent
BINDINGS = {
    "python": ("JSONRPC", "HTTP+JSON"),
    "typescript": ("JSONRPC", "HTTP+JSON"),
    "java": ("JSONRPC",),
}
SDK_VERSIONS = {"python": "1.3.1", "typescript": "1.3.0", "java": "1.5.1.Final"}
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


def lite_python():
    return os.environ.get(
        "A2ALITE_TEST_PYTHON", str(ROOT / "packages/python/.venv/bin/python")
    )


def official_python():
    if override := os.environ.get("A2ALITE_OFFICIAL_PYTHON"):
        return override
    reference = INTEROP / ".venv/bin/python"
    return str(reference) if reference.is_file() else lite_python()


def fixture(language, args):
    if language == "official-python":
        return [official_python(), "-I", str(INTEROP / "official_server.py"), *args]
    if language == "python":
        return [
            lite_python(),
            str(ROOT / "packages/python/tests/interop_fixture.py"),
            *args,
        ]
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
    require(result.get("jsonrpc") == "2.0", f"{method}: invalid JSON-RPC version")
    require(
        ("result" in result) != ("error" in result),
        f"{method}: invalid JSON-RPC envelope: {result}",
    )
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


def protocol_checks(url, language):
    status, _, body = request(url + "/.well-known/agent-card.json")
    require(status == 200, "Agent card unavailable")
    card = json.loads(body)
    advertised = [
        (i["protocolBinding"], i["protocolVersion"])
        for i in card["supportedInterfaces"]
    ]
    expected = [(binding, "1.0") for binding in BINDINGS[language]]
    require(
        sorted(advertised) == sorted(expected),
        f"Expected {expected} in card, got {advertised}",
    )
    for skill in card["skills"]:
        require(
            isinstance(skill.get("tags"), list),
            f"Skill {skill['id']} is missing its tags array",
        )
    url = next(
        i["url"]
        for i in card["supportedInterfaces"]
        if i["protocolBinding"] == "JSONRPC"
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
        status == 200 and headers.get_content_type() == "text/event-stream",
        "Invalid SSE response media type",
    )
    events = []
    for frame in stream.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        fields = [line[5:] for line in frame.split("\n") if line.startswith("data:")]
        if fields:
            events.append(json.loads("\n".join(fields)))
    require(
        events and events[0].get("result", {}).get("task", {}).get("id"),
        "SSE must start with a Task snapshot",
    )
    require(
        all(
            e.get("jsonrpc") == "2.0"
            and e.get("id") == identity
            and "result" in e
            and "error" not in e
            for e in events
        ),
        "Invalid SSE JSON-RPC envelope",
    )
    last = events[-1]["result"].get("statusUpdate", {})
    require(
        last.get("taskId") == events[0]["result"]["task"]["id"]
        and last.get("status", {}).get("state") == "TASK_STATE_COMPLETED",
        "SSE did not end with completion of the original Task",
    )
    failure = rpc(url, "SendMessage", message("fail"))
    require(
        "error" in failure
        or failure["result"].get("task", {}).get("status", {}).get("state")
        == "TASK_STATE_FAILED",
        "Failed skill reported success",
    )
    return {
        "discovery": True,
        "advertisedBindings": list(BINDINGS[language]),
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


def probe(command, marker, *, env=None):
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    require(
        result.returncode == 0,
        f"Probe exited {result.returncode}: {result.stdout[-2000:]}\n{result.stderr[-4000:]}",
    )
    records = [
        line[len(marker) :]
        for line in result.stdout.splitlines()
        if line.startswith(marker)
    ]
    require(
        len(records) == 1,
        f"Expected one {marker.strip()} record: {result.stdout[-2000:]}",
    )
    record = json.loads(records[0])
    for name in ("message", "task", "taskRead", "stream"):
        require(record.get(name) is True, f"Probe did not prove {name}: {record}")
    return record


def run_client(language, url):
    return probe(
        fixture(language, ["client", "--url", url]),
        "A2A_LITE_RESULT ",
        env=dict(os.environ, PYTHONPATH=str(ROOT / "packages/python/src")),
    )


def official_client(language, url, binding):
    args = ["--url", url, "--binding", binding]
    if language == "python":
        command = [official_python(), "-I", str(INTEROP / "official_sdk.py"), *args]
    elif language == "typescript":
        command = ["node", str(INTEROP / "official_js.mjs"), *args]
    else:
        executable = (
            INTEROP / "official-java/build/install/official-java/bin/official-java"
        )
        require(
            executable.is_file(),
            "Run packages/java/gradlew -p tests/interop/official-java installDist",
        )
        command = [str(executable), url, binding]
    record = probe(command, "A2A_LITE_OFFICIAL ")
    require(record.get("binding") == binding, f"Incorrect binding: {record}")
    require(
        record.get("sdkVersion") == SDK_VERSIONS[language],
        f"Unexpected SDK version: {record}",
    )
    require(
        record.get("taskNotFound") is True,
        f"Expected a typed error for the missing Task: {record}",
    )
    require(
        record.get("failure") is True,
        f"Expected the failing request to be checked: {record}",
    )
    return record


def matrix(args):
    rows = []

    def add(group, client, server_language, binding, reason=None):
        if server_language in BINDINGS and server_language not in args.languages:
            reason = "server excluded by --languages"
        rows.append(
            (
                group,
                {
                    "client": client,
                    "server": server_language,
                    "binding": binding,
                    "status": "skipped" if reason else "pending",
                    **({"reason": reason} if reason else {}),
                },
            )
        )

    for language, bindings in BINDINGS.items():
        for client in BINDINGS:
            omitted = (
                "client excluded by --languages"
                if client not in args.languages
                else None
            )
            add("pairs", client, language, "JSONRPC", omitted)
        diagnostic = "--skip-protocol" if args.skip_protocol else None
        add("protocol", "wire", language, "JSONRPC", diagnostic)
        for binding in bindings:
            for sdk in SDK_VERSIONS:
                extended = sdk == "java" and not args.extended
                add(
                    "officialSdk",
                    sdk,
                    language,
                    binding,
                    diagnostic or ("requires --extended" if extended else None),
                )
        reverse = None if args.extended else "requires --extended"
        if language not in args.languages:
            reverse = "client excluded by --languages"
        add("officialServer", language, "official-python", "JSONRPC", reverse)
    return rows


def run_case(group, row, url):
    client = row["client"]
    if group == "protocol":
        return protocol_checks(url, row["server"])
    if group == "officialSdk":
        return official_client(client, url, row["binding"])
    record = run_client(client, url)
    if group == "officialServer":
        from reverse_errors import check_error

        check_error(client, url, fixture)
        status, _, raw = request(url + "/.well-known/agent-card.json")
        server_version = json.loads(raw)["version"]
        require(
            status == 200 and server_version == SDK_VERSIONS["python"],
            f"Unexpected official server version: {server_version}",
        )
        record.update(
            serverSdk="a2a-sdk",
            serverSdkVersion=server_version,
            failure=True,
            tenant=True,
        )
    return record


def run_server_cases(language, logs, cases, errors):
    try:
        with server(language, logs) as runtime:
            for group, row in cases:
                try:
                    checks = run_case(group, row, runtime.url)
                    row.update(checks, status="passed")
                except Exception as exc:
                    row.update(status="failed", error=str(exc) or repr(exc))
                print(json.dumps({"gate": group, **row}), flush=True)
    except Exception as exc:
        errors.append(f"{language} server: {exc}")
        for _, row in cases:
            if row["status"] == "pending":
                row.update(status="skipped", reason=f"server unavailable: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages", nargs="+", choices=BINDINGS, default=list(BINDINGS)
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-protocol",
        action="store_true",
        help="Diagnostic only: run Lite pairs alone",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Include the official Java client and independent server",
    )
    args = parser.parse_args()
    if args.skip_protocol and args.extended:
        parser.error("--extended and --skip-protocol select conflicting scopes")
    rows = matrix(args)
    report = {
        "schemaVersion": 2,
        **source_state(),
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "cpuCount": os.cpu_count(),
        "success": False,
        "fullMatrixPassed": False,
        "errors": [],
    }
    for group, row in rows:
        report.setdefault(group, []).append(row)
    selected = [(group, row) for group, row in rows if row["status"] == "pending"]
    try:
        with tempfile.TemporaryDirectory(prefix="a2alite-interop-") as logs:
            for language in (*BINDINGS, "official-python"):
                cases = [
                    (group, row) for group, row in selected if row["server"] == language
                ]
                if cases:
                    run_server_cases(language, logs, cases, report["errors"])
        report["success"] = (
            bool(selected)
            and not report["errors"]
            and all(row["status"] == "passed" for _, row in selected)
        )
        report["fullMatrixPassed"] = report["success"] and all(
            row["status"] == "passed" for _, row in rows
        )
    finally:
        for _, row in rows:
            if row["status"] == "pending":
                row.update(status="skipped", reason="run interrupted")
        report["counts"] = {
            status: sum(row["status"] == status for _, row in rows)
            for status in ("passed", "failed", "skipped")
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps({"counts": report["counts"], "errors": report["errors"]}),
            flush=True,
        )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
