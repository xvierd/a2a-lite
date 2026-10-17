#!/usr/bin/env python3
"""Reproducible local capacity experiment; measurements are not production SLOs."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

from run import ROOT, message, request, server


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def sample(url, workload, index):
    started = time.perf_counter()
    try:
        method = "SendStreamingMessage" if workload == "stream" else "SendMessage"
        skill = {
            "message": "greet",
            "task": "taskProbe",
            "io": "delay",
            "stream": "stream",
        }[workload]
        status, _, body = request(
            url,
            {
                "jsonrpc": "2.0",
                "id": index,
                "method": method,
                "params": message(skill, {"text": "hello"} if skill == "greet" else {}),
            },
        )
        if status != 200:
            return time.perf_counter() - started, f"http_{status}", len(body)
        if workload == "stream":
            ok = "TASK_STATE_COMPLETED" in body and '"error"' not in body
        else:
            result = json.loads(body)
            ok = "result" in result and "error" not in result
            if workload == "task":
                ok = (
                    ok
                    and result["result"].get("task", {}).get("status", {}).get("state")
                    == "TASK_STATE_COMPLETED"
                )
            else:
                parts = result.get("result", {}).get("message", {}).get("parts", [])
                expected = "hello" if workload == "message" else "ok"
                values = []
                for part in parts:
                    value = part.get("text")
                    try:
                        value = json.loads(value)
                    except (TypeError, ValueError):
                        pass
                    values.append(value)
                ok = ok and expected in values
        return (
            time.perf_counter() - started,
            None if ok else "protocol_failure",
            len(body),
        )
    except Exception as exc:
        return time.perf_counter() - started, type(exc).__name__, 0


def measure(url, workload, count, concurrency):
    for index in range(5):
        _, error, _ = sample(url, workload, -index - 1)
        if error:
            raise RuntimeError(f"{workload} warmup failed: {error}")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples = list(
            pool.map(lambda index: sample(url, workload, index), range(count))
        )
    elapsed = time.perf_counter() - started
    latencies = [seconds * 1000 for seconds, error, _ in samples if error is None]
    errors = {}
    for _, error, _ in samples:
        if error:
            errors[error] = errors.get(error, 0) + 1
    return {
        "workload": workload,
        "requests": count,
        "concurrency": concurrency,
        "seconds": elapsed,
        "completedPerSecond": len(latencies) / elapsed,
        "p50Ms": percentile(latencies, 0.5),
        "p95Ms": percentile(latencies, 0.95),
        "p99Ms": percentile(latencies, 0.99),
        "errorRate": sum(errors.values()) / count,
        "errors": errors,
        "responseBytes": sum(size for _, _, size in samples),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=("python", "typescript", "java"),
        default=["python", "typescript", "java"],
    )
    parser.add_argument(
        "--workloads",
        nargs="+",
        choices=("message", "task", "io", "stream"),
        default=["message", "task", "io", "stream"],
    )
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.requests <= 100000 or not 1 <= args.concurrency <= 256:
        parser.error("requests must be 1..100000 and concurrency 1..256")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            text=True,
        )
    )
    report = {
        "schemaVersion": 1,
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gitCommit": commit,
        "trackedWorktreeDirty": dirty,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpuCount": os.cpu_count(),
        "scope": "Loopback, one authenticated memory-backed server; no TLS, database or LLM. io waits 20ms. Not a production SLO.",
        "measurements": [],
        "complete": False,
        "success": False,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="a2alite-load-") as logs:
            for language in args.languages:
                with server(language, logs) as runtime:
                    url = runtime.url
                    for workload in args.workloads:
                        result = {
                            "language": language,
                            **measure(url, workload, args.requests, args.concurrency),
                        }
                        report["measurements"].append(result)
                        print(json.dumps(result), flush=True)
        report["complete"] = True
        report["success"] = all(item["errorRate"] == 0 for item in report["measurements"])
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
