"""Add fixture credentials to the pinned TCK's two synchronous HTTP clients."""

import os
from urllib.parse import urlsplit

import pytest


@pytest.fixture(autouse=True, scope="session")
def fixture_auth(transport_clients, sut_host):
    origin = urlsplit(sut_host)
    assert origin.scheme == "http" and origin.hostname == "127.0.0.1"

    # This revision of the upstream TCK exposes no authentication CLI flag.
    # A request hook also covers streaming and checks redirect destinations.
    def authenticate(request):
        assert request.url.scheme == origin.scheme
        assert request.url.host == origin.hostname and request.url.port == origin.port
        request.headers["X-API-Key"] = os.environ["A2ALITE_TCK_FIXTURE_TOKEN"]

    for transport in transport_clients.values():
        transport._client.event_hooks["request"].append(authenticate)
