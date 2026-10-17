#!/usr/bin/env python3
"""Audit the resolved Java fixture dependency graph against the public OSV API."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classpath",
        type=Path,
        default=ROOT / "packages/java/build/interop-classpath.txt",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coordinates = set()
    for item in args.classpath.read_text().split(os.pathsep):
        marker = "/modules-2/files-2.1/"
        normalized = item.replace("\\", "/")
        if marker in normalized:
            parts = normalized.split(marker, 1)[1].split("/")
            if len(parts) >= 3:
                coordinates.add((parts[0] + ":" + parts[1], parts[2]))
    if not coordinates:
        raise RuntimeError(
            "No resolved Maven coordinates found; run writeInteropClasspath first"
        )
    queries = [
        {"package": {"name": name, "ecosystem": "Maven"}, "version": version}
        for name, version in sorted(coordinates)
    ]
    report = {
        "schemaVersion": 1,
        "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "https://api.osv.dev/v1/querybatch",
        "scope": "Resolved Java test runtime, including the standalone server and PostgreSQL driver",
        "dependencies": [],
        "success": False,
    }
    try:
        request = urllib.request.Request(
            report["source"],
            data=json.dumps({"queries": queries}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            results = json.load(response)["results"]
        if len(results) != len(queries):
            raise RuntimeError("OSV returned an incomplete result")
        for query, result in zip(queries, results):
            report["dependencies"].append(
                {
                    **query,
                    "advisories": [item["id"] for item in result.get("vulns", [])],
                }
            )
        findings = [item for item in report["dependencies"] if item["advisories"]]
        for item in findings:
            print(
                item["package"]["name"], item["version"], ", ".join(item["advisories"])
            )
        report["success"] = not findings
        print(
            f"{len(findings)} dependencies with known advisories among {len(queries)} resolved dependencies"
        )
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
