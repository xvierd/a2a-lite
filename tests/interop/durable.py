#!/usr/bin/env python3
"""PostgreSQL process crash and backup/restore gate using disposable databases."""

import argparse
import contextlib
import datetime as dt
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
from uuid import uuid4

from run import HTTP, ROOT, message, require, rpc, server, source_state

DB_USER = "a2alite_test"
DB_PASSWORD = "a2alite_local_test_only"  # Only for the disposable localhost container.


def docker(*args, data=None):
    return subprocess.run(
        ["docker", *args],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=120,
    ).stdout


@contextlib.contextmanager
def postgres(existing=None):
    name = existing or "a2alite-gate-" + uuid4().hex[:12]
    if not existing:
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            "a2alite.test=contract",
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_USER=" + DB_USER,
            "--env",
            "POSTGRES_PASSWORD=" + DB_PASSWORD,
            "--env",
            "POSTGRES_DB=a2alite_test",
            "postgres:17",
        )
    try:
        info = json.loads(docker("inspect", name))[0]
        require(
            info["Config"]["Labels"].get("a2alite.test")
            in ("contract", "production-path"),
            "Refusing a container not labeled as an A2A Lite test instance",
        )
        mapping = info["NetworkSettings"]["Ports"]["5432/tcp"][0]
        require(
            mapping["HostIp"] == "127.0.0.1",
            "Test PostgreSQL must be bound to localhost",
        )
        port = int(mapping["HostPort"])
        deadline = time.monotonic() + 30
        while True:
            try:
                docker("exec", name, "pg_isready", "-U", DB_USER)
                break
            except subprocess.CalledProcessError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        yield name, port
    finally:
        if not existing:
            docker("rm", "--force", "--volumes", name)


def sql(container, statement):
    return docker(
        "exec",
        container,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        DB_USER,
        "-d",
        "postgres",
        "-c",
        statement,
    )


def environment(language, port, database):
    base = f"postgresql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{port}/{database}"
    url = base
    if language == "python":
        url = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif language == "java":
        url = f"jdbc:postgresql://127.0.0.1:{port}/{database}"
    return {
        "A2ALITE_INTEROP_POSTGRES_DSN": url,
        "A2ALITE_POSTGRES_USER": DB_USER,
        "A2ALITE_POSTGRES_PASSWORD": DB_PASSWORD,
    }, base


def migrate(language, dsn):
    if language == "typescript":
        cli = ROOT / "packages/typescript/node_modules/@a2a-js/sdk/dist/cli/a2a_db.js"
        subprocess.run(
            ["node", str(cli), "upgrade"],
            cwd=ROOT,
            env=dict(os.environ, DATABASE_URL=dsn),
            check=True,
            capture_output=True,
            timeout=60,
        )
        subprocess.run(
            [
                "node",
                str(ROOT / "packages/typescript/node_modules/tsx/dist/cli.mjs"),
                str(Path(__file__).with_name("migrate-typescript.mts")),
            ],
            cwd=ROOT,
            env=dict(os.environ, DATABASE_URL=dsn),
            check=True,
            capture_output=True,
            timeout=60,
        )
    # Python/Java fixture constructors explicitly migrate only their disposable database.


def package_tests(language, env):
    child_env = dict(os.environ, **env)
    child_env["A2ALITE_POSTGRES_DSN"] = env["A2ALITE_INTEROP_POSTGRES_DSN"]
    if language == "python":
        package = ROOT / "packages/python"
        python = os.environ.get(
            "A2ALITE_TEST_PYTHON", str(package / ".venv/bin/python")
        )
        tests = sorted(
            set(package.glob("tests/test_persistence*.py"))
            | set(package.glob("tests/test_recovery*.py"))
        )
        command = [python, "-m", "pytest", *[str(path) for path in tests], "-q"]
    elif language == "typescript":
        package = ROOT / "packages/typescript"
        tests = sorted(package.glob("tests/postgres*.test.ts"))
        command = [
            str(package / "node_modules/.bin/vitest"),
            "run",
            *[str(path) for path in tests],
        ]
    else:
        package = ROOT / "packages/java"
        tests = sorted(package.glob("src/test/java/**/*Postgres*Test.java"))
        command = [
            str(package / "gradlew"),
            "test",
            "--tests",
            "*Postgres*",
            "--rerun-tasks",
            "--no-daemon",
        ]
    require(tests, f"No PostgreSQL contract tests found for {language}")
    result = subprocess.run(
        command, cwd=package, env=child_env, text=True, capture_output=True, timeout=600
    )
    require(
        result.returncode == 0,
        f"{language} database tests failed:\n{result.stdout[-6000:]}\n{result.stderr[-3000:]}",
    )


def read_contract(url, task_id, config_id):
    read = rpc(url, "GetTask", {"id": task_id}, "interop-rotated")
    require(read.get("result", {}).get("id") == task_id, f"Task was lost: {read}")
    require(
        read["result"]["status"]["state"] == "TASK_STATE_COMPLETED",
        "Completed state changed",
    )
    config = rpc(
        url,
        "GetTaskPushNotificationConfig",
        {"taskId": task_id, "id": config_id},
        "interop-rotated",
    )
    require(
        config.get("result", {}).get("token") == "fixture-token",
        "Callback encryption/key restore failed",
    )
    for method, params in (
        ("GetTask", {"id": task_id}),
        ("GetTaskPushNotificationConfig", {"taskId": task_id, "id": config_id}),
    ):
        require(
            "error" in rpc(url, method, params, "interop-other"),
            "Restoration lost owner isolation",
        )
    require(
        task_id not in json.dumps(rpc(url, "ListTasks", {}, "interop-other")),
        "Restoration exposed tasks in listing",
    )


def open_stream(url, method, params):
    body = {"jsonrpc": "2.0", "id": uuid4().hex, "method": method, "params": params}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "A2A-Version": "1.0",
            "X-API-Key": "interop-secret",
        },
    )
    response = HTTP.open(req, timeout=20)
    if "text/event-stream" not in response.headers.get("Content-Type", ""):
        data = response.read().decode()
        response.close()
        raise AssertionError(f"{method} did not open a stream: {data}")
    return response


def initial_task(stream):
    for line in stream:
        if line.startswith(b"data:"):
            event = json.loads(line[5:].strip())
            task_id = event.get("result", {}).get("task", {}).get("id")
            require(task_id, f"Initial Task snapshot missing: {event}")
            return task_id
    raise AssertionError("Stream ended before the first Task snapshot")


def active_contract(language, logs, env, recovery_timeout):
    with server(language, logs, env) as first, server(language, logs, env) as second:
        with open_stream(
            first.url, "SendStreamingMessage", message("hold")
        ) as original:
            task_id = initial_task(original)
            with open_stream(
                second.url, "SubscribeToTask", {"id": task_id}
            ) as subscription:
                require(
                    initial_task(subscription) == task_id,
                    "Replica B subscribed to the wrong task",
                )
                canceled = rpc(second.url, "CancelTask", {"id": task_id})
                require(
                    canceled.get("result", {}).get("status", {}).get("state")
                    == "TASK_STATE_CANCELED",
                    f"Remote cancellation failed: {canceled}",
                )
                remote_events = subscription.read().decode()
                local_events = original.read().decode()
                require(
                    "TASK_STATE_CANCELED" in remote_events,
                    f"Remote subscription lost cancellation: {remote_events[-4000:]}",
                )
                require(
                    "TASK_STATE_CANCELED" in local_events,
                    f"Owning replica did not observe cancellation: {local_events[-4000:]}",
                )
            # A late worker completion must not overwrite the accepted cancellation.
            time.sleep(0.2)
            require(
                rpc(second.url, "GetTask", {"id": task_id})["result"]["status"]["state"]
                == "TASK_STATE_CANCELED",
                "A stale producer overwrote cancellation",
            )
        with open_stream(
            first.url, "SendStreamingMessage", message("hold")
        ) as interrupted:
            abandoned_id = initial_task(interrupted)
            first.crash()
        started = time.monotonic()
        while time.monotonic() - started < recovery_timeout:
            task = rpc(second.url, "GetTask", {"id": abandoned_id}).get("result", {})
            if task.get("status", {}).get("state") == "TASK_STATE_FAILED":
                return {
                    "remoteSubscribe": True,
                    "remoteCancel": True,
                    "terminalFence": True,
                    "ordinaryCrashExplicitlyFailed": True,
                    "observedReconciliationSeconds": time.monotonic() - started,
                }
            require(
                task.get("status", {}).get("state") != "TASK_STATE_COMPLETED",
                "Killed ordinary skill reported completion",
            )
            time.sleep(0.2)
        raise AssertionError(
            f"Killed {language} producer did not become FAILED within {recovery_timeout}s"
        )


def qualify(
    language,
    container,
    port,
    logs,
    include_package_tests=False,
    active=False,
    recovery_timeout=60,
):
    suffix = uuid4().hex[:12]
    source = f"a2alite_gate_{language}_{suffix}"
    restored = source + "_restored"
    sql(container, f'CREATE DATABASE "{source}"')
    sql(container, f'CREATE DATABASE "{restored}"')
    try:
        env, dsn = environment(language, port, source)
        if active:
            env["A2ALITE_INTEROP_DISTRIBUTED"] = "1"
        if include_package_tests:
            package_tests(language, env)
        migrate(language, dsn)
        with server(language, logs, env) as first:
            created = rpc(first.url, "SendMessage", message("taskProbe"))
            task_id = created.get("result", {}).get("task", {}).get("id")
            require(task_id, f"Durable task creation failed: {created}")
            config_id = "restore-contract"
            configured = rpc(
                first.url,
                "CreateTaskPushNotificationConfig",
                {
                    "taskId": task_id,
                    "id": config_id,
                    "url": "https://8.8.8.8/a2alite-restore",
                    "token": "fixture-token",
                },
            )
            require(
                "error" not in configured,
                f"Durable callback config failed: {configured}",
            )
            paused = rpc(first.url, "SendMessage", message("pause"))
            paused_task = paused.get("result", {}).get("task", {})
            paused_id = paused_task.get("id")
            require(
                paused_id
                and paused_task.get("status", {}).get("state")
                == "TASK_STATE_INPUT_REQUIRED",
                f"Task did not pause for input: {paused}",
            )
            continuation = message("pause", {"resume": True})
            continuation["message"]["taskId"] = paused_id
            with server(language, logs, env) as second:
                read_contract(second.url, task_id, config_id)
                require(
                    "error"
                    in rpc(second.url, "SendMessage", continuation, "interop-other"),
                    "Another principal continued a paused task",
                )
                first.crash()
                read_contract(second.url, task_id, config_id)
                resumed = rpc(
                    second.url, "SendMessage", continuation, "interop-rotated"
                )
                resumed_task = resumed.get("result", {}).get("task", {})
                require(
                    resumed_task.get("id") == paused_id
                    and resumed_task.get("status", {}).get("state")
                    == "TASK_STATE_COMPLETED",
                    f"Paused task did not continue on another replica with its original ID: {resumed}",
                )
        # A fresh process must read a completed Task after SIGKILL, without replaying the skill.
        with server(language, logs, env) as restarted:
            read_contract(restarted.url, task_id, config_id)
        dump = docker("exec", container, "pg_dump", "-Fc", "-U", DB_USER, "-d", source)
        docker(
            "exec",
            "-i",
            container,
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "-U",
            DB_USER,
            "-d",
            restored,
            data=dump,
        )
        restored_env, _ = environment(language, port, restored)
        with server(language, logs, restored_env) as recovered:
            read_contract(recovered.url, task_id, config_id)
        active_result = (
            active_contract(language, logs, env, recovery_timeout) if active else {}
        )
        return {
            "language": language,
            "twoReplicaRead": True,
            "processKill": True,
            "restart": True,
            "pgDumpRestore": True,
            "callbackDecryption": True,
            "ownerIsolation": True,
            "pausedTaskContinuation": True,
            "continuationOwnerIsolation": True,
            "packageDatabaseTests": include_package_tests,
            "activeExecutionTested": active,
            **active_result,
        }
    finally:
        for database in (source, restored):
            sql(container, f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=("python", "typescript", "java"),
        default=["python", "typescript", "java"],
    )
    parser.add_argument(
        "--container",
        help="Reuse an existing labeled A2A Lite test container; do not stop it",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--package-tests",
        action="store_true",
        help="Also run language database contract suites against each disposable database",
    )
    parser.add_argument(
        "--active",
        action="store_true",
        help="Also prove remote subscriptions/cancellation and crash reconciliation",
    )
    parser.add_argument("--recovery-timeout", type=float, default=60)
    parser.add_argument(
        "--logs",
        type=Path,
        help="Keep fixture logs in this directory for failure diagnosis",
    )
    args = parser.parse_args()
    if not math.isfinite(args.recovery_timeout) or args.recovery_timeout <= 0:
        parser.error("--recovery-timeout must be finite and positive")
    if args.logs:
        args.logs.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": 1,
        **source_state(),
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profiles": [],
        "success": False,
    }
    try:
        log_context = (
            contextlib.nullcontext(str(args.logs))
            if args.logs
            else tempfile.TemporaryDirectory(prefix="a2alite-durable-")
        )
        with postgres(args.container) as (container, port), log_context as logs:
            for language in args.languages:
                result = qualify(
                    language,
                    container,
                    port,
                    logs,
                    args.package_tests,
                    args.active,
                    args.recovery_timeout,
                )
                report["profiles"].append(result)
                print(json.dumps(result), flush=True)
        report["success"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
