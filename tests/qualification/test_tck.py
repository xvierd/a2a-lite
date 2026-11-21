"""Run selected upstream TCK tests unmodified, retaining per-case JUnit evidence."""

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from run import TOKEN, request

SHA = "5e6f37c2d38eb3d7684686243c34d365c83df49b"
HERE = Path(__file__).resolve().parent
BASE = "tests/compatibility/"
FORMAT = "core_operations/test_transport_behavior.py::"
RPC_ERRORS = "jsonrpc/test_error_codes.py::TestJsonRpcErrorCodeMappings::"
HTTP_STATUS = "http_json/test_http_status.py::TestHttpJsonStatusCodes::"
SERIALIZATION = [
    "core_operations/test_data_model.py::TestCamelCaseFieldNames",
    "core_operations/test_data_model.py::TestEnumSerialization",
]
CASES = {
    "cards": (6, ["agent_card/test_agent_card.py"]),
    "jsonrpc": (
        10,
        [
            *SERIALIZATION,
            FORMAT + "TestJsonRpcFormat",
            FORMAT + "TestJsonRpcStreaming",
            "jsonrpc/test_sse_streaming.py::TestSseStreamingFormat",
            "jsonrpc/test_sse_streaming.py::TestSseSubscribeToTask::test_subscribe_nonexistent_task_returns_error",
            RPC_ERRORS + "test_task_not_found_error",
            RPC_ERRORS + "test_task_not_cancelable_error",
        ],
    ),
    "http_json": (
        7,
        [
            *SERIALIZATION,
            FORMAT + "TestRestFormat::test_response_validates_against_schema",
            FORMAT + "TestRestStreaming",
            HTTP_STATUS + "test_success_returns_2xx",
            HTTP_STATUS + "test_task_not_found_returns_404",
            HTTP_STATUS + "test_cancel_missing_task_returns_404",
        ],
    ),
}


@pytest.fixture(scope="module")
def checkout(pytestconfig, record_testsuite_property):
    path = pytestconfig.getoption("--tck-checkout")
    if not path:
        pytest.fail(
            "Pass --tck-checkout pointing to the prepared upstream checkout; see README.md"
        )
    root = Path(path).resolve()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    assert revision == SHA, f"TCK {revision}, expected {SHA}"
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    )
    assert not dirty, f"TCK checkout has local changes: {dirty}"
    record_testsuite_property("tckRevision", revision)
    return root


@pytest.fixture(scope="module")
def results(pytestconfig, tmp_path_factory):
    path = pytestconfig.getoption("--tck-results")
    if not path:
        return tmp_path_factory.mktemp("tck-reports")
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def qualify(checkout, results, url, language, profile):
    count, cases = CASES[profile]
    xml = results / f"{language}-{profile}.xml"
    cmd = [
        str(checkout / ".venv/bin/python"),
        "-m",
        "pytest",
        "-q",
        "-m",
        "must",
        "--tb=short",
        "--sut-host=" + url,
        "--junitxml=" + str(xml),
    ]
    if profile != "cards":
        cmd.extend(["-p", "tck_fixture_auth", "--transport=" + profile])
    cmd.extend(BASE + case for case in cases)
    env = {
        **os.environ,
        "PYTHONPATH": str(HERE),
        "A2ALITE_TCK_FIXTURE_TOKEN": TOKEN,
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
        "PYTEST_ADDOPTS": "",
        "PYTEST_PLUGINS": "",
    }
    proc = subprocess.run(
        cmd,
        cwd=checkout,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    (results / f"{language}-{profile}.log").write_text(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    cases_run = ET.parse(xml).findall(".//testcase")
    assert len(cases_run) == count, (
        f"Expected {count} upstream tests, got {len(cases_run)}"
    )
    for case in cases_run:
        problem = next(
            (child for child in case if child.tag in ("skipped", "error", "failure")),
            None,
        )
        assert problem is None, (
            f"{case.attrib['name']}: {problem.tag}: {problem.get('message')}"
        )


def test_cards(checkout, results, peer, language):
    qualify(checkout, results, peer, language, "cards")
    # The upstream schema accepts disappearance of a binding when one remains.
    status, _, raw = request(peer + "/.well-known/agent-card.json", token=None)
    assert status == 200
    published = {
        (i["protocolBinding"], i["protocolVersion"])
        for i in json.loads(raw)["supportedInterfaces"]
    }
    expected = {("JSONRPC", "1.0")}
    if language != "java":
        expected.add(("HTTP+JSON", "1.0"))
    assert published == expected


def test_jsonrpc(checkout, results, text_peer, language):
    qualify(checkout, results, text_peer, language, "jsonrpc")


@pytest.mark.parametrize(
    "language", ["python", "typescript"], indirect=True, scope="module"
)
def test_http_json(checkout, results, text_peer, language):
    qualify(checkout, results, text_peer, language, "http_json")
