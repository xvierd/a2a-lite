"""Request-scoped credentials for A2A clients, bounded to trusted origins."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

CredentialProvider = Callable[[str], Mapping[str, str] | Awaitable[Mapping[str, str]]]


def origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("A2A endpoints require HTTP(S), without userinfo or fragments")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


@dataclass(frozen=True)
class ClientConfig:
    """Credentials are resolved per request; redirects are never followed.

    Register separate configurations for distinct audiences. Cross-origin card
    endpoints require an explicit allowed_origins entry before receiving headers.
    """

    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    credential_provider: CredentialProvider | None = field(default=None, repr=False)
    tenant: str = ""
    allowed_origins: frozenset[str] = field(default_factory=frozenset)
    _origin: str | None = field(default=None, repr=False)

    def bind(self, url: str) -> ClientConfig:
        origin(url)
        return self if self._origin is not None else replace(self, _origin=url, headers=dict(self.headers))

    def check_endpoint(self, url: str) -> None:
        destination = origin(url)
        trusted = {origin(item) for item in self.allowed_origins}
        if self._origin is not None:
            trusted.add(origin(self._origin))
        if trusted and destination not in trusted:
            raise ValueError("Discovered A2A endpoint has an untrusted origin; configure allowed_origins explicitly")

    async def request_headers(self, url: str, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        self.check_endpoint(url)
        headers = {**self.headers, **(extra or {})}
        if self.credential_provider:
            supplied = self.credential_provider(url)
            if inspect.isawaitable(supplied):
                supplied = await supplied
            headers.update(supplied)
        # Protocol negotiation cannot be changed by stale credential headers.
        headers = {key: value for key, value in headers.items() if key.lower() != "a2a-version"}
        return {**headers, "A2A-Version": "1.0"}

    def request_params(self, params: dict) -> dict:
        return {**params, **({"tenant": self.tenant} if self.tenant else {})}
