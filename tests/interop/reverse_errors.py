"""Run the tenant and streaming-error assertions with the selected Lite runtime."""

import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {
    "python": "reverse_client.py",
    "typescript": "reverse_client.mts",
    "java": "reverse_client.java",
}


def check_error(language, url, fixture):
    # The normal fixture command ends in its script or Java main class. Reuse its
    # interpreter, tsx loader or Java classpath for this second Lite client.
    command = [*fixture(language, [])[:-1], str(HERE / SOURCES[language]), url]
    result = subprocess.run(
        command,
        cwd=HERE.parents[1],
        env=dict(os.environ, PYTHONPATH=str(HERE.parents[1] / "packages/python/src")),
        text=True,
        capture_output=True,
        timeout=60,
    )
    if result.returncode or result.stdout.splitlines().count("A2A_LITE_STREAM_ERROR_VERIFIED") != 1:
        raise AssertionError(
            f"{language} discovery/tenant/SSE error probe failed: {result.stdout[-2000:]}\n{result.stderr[-4000:]}"
        )
