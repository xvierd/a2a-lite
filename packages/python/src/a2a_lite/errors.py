"""
Structured error types for A2A Lite.

Provides clear, actionable error messages for common failure modes:
- Unknown skill names
- Parameter validation failures
- Authentication requirements

All errors extend A2ALiteError and provide a to_response() method
for structured JSON responses.
"""

from __future__ import annotations

from typing import Any


class A2ALiteError(Exception):
    """Base error for all A2A Lite errors."""

    def to_response(self) -> dict[str, Any]:
        """Convert error to a structured response dict."""
        return {
            "error": str(self),
            "type": type(self).__name__,
        }


class SkillNotFoundError(A2ALiteError):
    """Raised when a requested skill does not exist.

    Args:
        skill: The skill name that was requested.
        available_skills: Dict mapping skill names to their descriptions.
    """

    def __init__(
        self,
        skill: str,
        available_skills: dict[str, str] | None = None,
    ) -> None:
        self.skill = skill
        self.available_skills = available_skills or {}
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = [f"Unknown skill '{self.skill}'."]
        if self.available_skills:
            lines.append("Available skills:")
            for name, desc in self.available_skills.items():
                lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def to_response(self) -> dict[str, Any]:
        return {
            "error": f"Unknown skill '{self.skill}'",
            "type": "SkillNotFoundError",
            "available_skills": list(self.available_skills.keys()),
            "details": dict(self.available_skills.items()),
        }


class ParamValidationError(A2ALiteError):
    """Raised when skill parameters fail validation.

    Args:
        skill: The skill name that was called.
        errors: List of individual validation error dicts.
    """

    def __init__(
        self,
        skill: str,
        errors: list[dict[str, Any]],
    ) -> None:
        self.skill = skill
        self.errors = errors
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = [f"Skill '{self.skill}' parameter error:"]
        for err in self.errors:
            field = err.get("field", "unknown")
            message = err.get("message", "validation failed")
            lines.append(f"  - '{field}': {message}")
        return "\n".join(lines)

    def to_response(self) -> dict[str, Any]:
        return {
            "error": f"Skill '{self.skill}' parameter validation failed",
            "type": "ParamValidationError",
            "skill": self.skill,
            "validation_errors": self.errors,
        }


class RemoteAgentError(A2ALiteError):
    """Raised when a remote agent returns an error response.

    Args:
        message: Human-readable error description.
        response: The raw error response dict from the remote agent.
    """

    def __init__(
        self,
        message: str,
        response: dict[str, Any] | None = None,
    ) -> None:
        self.response = response or {}
        super().__init__(message)

    def to_response(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "type": "RemoteAgentError",
            "remote_response": self.response,
        }


class AuthRequiredError(A2ALiteError):
    """Raised when authentication is required but not provided.

    Args:
        scheme_info: Description of the required auth scheme.
        detail: Additional detail about the auth requirement.
    """

    def __init__(
        self,
        scheme_info: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.scheme_info = scheme_info or "authentication"
        self.detail = detail
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        msg = f"Authentication required. This agent uses {self.scheme_info}."
        if self.detail:
            msg += f"\n{self.detail}"
        return msg

    def to_response(self) -> dict[str, Any]:
        resp: dict[str, Any] = {
            "error": "Authentication required",
            "type": "AuthRequiredError",
            "scheme": self.scheme_info,
        }
        if self.detail:
            resp["detail"] = self.detail
        return resp
