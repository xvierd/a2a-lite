"""Loopback fixtures shared by the ADK and TCK qualification tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interop"))
import run as interop


def pytest_addoption(parser):
    parser.addoption(
        "--tck-checkout", help="Path to the pinned TCK checkout with a locked .venv"
    )
    parser.addoption(
        "--tck-results",
        help="Directory for per-server upstream JUnit and pytest output",
    )


@pytest.fixture(scope="session", autouse=True)
def record_lite_version(record_testsuite_property):
    for key, value in interop.source_state().items():
        record_testsuite_property(key, value)


@pytest.fixture(scope="module", params=("python", "typescript", "java"))
def language(request):
    return request.param


@pytest.fixture(scope="module")
def peer(language, tmp_path_factory):
    with interop.server(
        language, tmp_path_factory.mktemp(language), {"A2ALITE_INTEROP_TEXT_ENTRY": "0"}
    ) as runtime:
        yield runtime.url


@pytest.fixture(scope="module")
def text_peer(language, tmp_path_factory):
    with interop.server(
        language, tmp_path_factory.mktemp(language), {"A2ALITE_INTEROP_TEXT_ENTRY": "1"}
    ) as runtime:
        yield runtime.url
