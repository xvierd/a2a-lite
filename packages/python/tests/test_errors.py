"""
Tests for the structured error types.
"""
import pytest

from a2a_lite.errors import (
    A2ALiteError,
    SkillNotFoundError,
    ParamValidationError,
    AuthRequiredError,
)


class TestA2ALiteError:
    def test_base_error(self):
        err = A2ALiteError("something went wrong")
        assert str(err) == "something went wrong"

    def test_base_to_response(self):
        err = A2ALiteError("oops")
        resp = err.to_response()
        assert resp["error"] == "oops"
        assert resp["type"] == "A2ALiteError"

    def test_is_exception(self):
        err = A2ALiteError("test")
        assert isinstance(err, Exception)


class TestSkillNotFoundError:
    def test_basic_message(self):
        err = SkillNotFoundError("greet")
        assert "greet" in str(err)
        assert "Unknown skill" in str(err)

    def test_with_available_skills(self):
        err = SkillNotFoundError(
            "greet",
            available_skills={"hello": "Say hello", "calc": "Do math"},
        )
        msg = str(err)
        assert "greet" in msg
        assert "hello" in msg
        assert "calc" in msg
        assert "Say hello" in msg

    def test_to_response(self):
        err = SkillNotFoundError(
            "greet",
            available_skills={"hello": "Say hello", "calc": "Do math"},
        )
        resp = err.to_response()
        assert resp["type"] == "SkillNotFoundError"
        assert "greet" in resp["error"]
        assert "hello" in resp["available_skills"]
        assert "calc" in resp["available_skills"]
        assert resp["details"]["hello"] == "Say hello"

    def test_to_response_no_available(self):
        err = SkillNotFoundError("greet")
        resp = err.to_response()
        assert resp["available_skills"] == []

    def test_is_a2a_lite_error(self):
        err = SkillNotFoundError("greet")
        assert isinstance(err, A2ALiteError)


class TestParamValidationError:
    def test_basic_message(self):
        err = ParamValidationError("create_user", [
            {"field": "email", "message": "expected str, got int"},
            {"field": "age", "message": "field required"},
        ])
        msg = str(err)
        assert "create_user" in msg
        assert "email" in msg
        assert "age" in msg

    def test_to_response(self):
        errors = [
            {"field": "email", "message": "expected str, got int"},
            {"field": "age", "message": "field required"},
        ]
        err = ParamValidationError("create_user", errors)
        resp = err.to_response()
        assert resp["type"] == "ParamValidationError"
        assert resp["skill"] == "create_user"
        assert len(resp["validation_errors"]) == 2
        assert resp["validation_errors"][0]["field"] == "email"

    def test_empty_errors(self):
        err = ParamValidationError("test", [])
        resp = err.to_response()
        assert resp["validation_errors"] == []

    def test_is_a2a_lite_error(self):
        err = ParamValidationError("test", [])
        assert isinstance(err, A2ALiteError)


class TestAuthRequiredError:
    def test_basic_message(self):
        err = AuthRequiredError()
        assert "Authentication required" in str(err)
        assert "authentication" in str(err)

    def test_with_scheme_info(self):
        err = AuthRequiredError(scheme_info="API Key auth")
        assert "API Key auth" in str(err)

    def test_with_detail(self):
        err = AuthRequiredError(
            scheme_info="API Key auth",
            detail="Pass your key via the 'X-API-Key' header.",
        )
        msg = str(err)
        assert "API Key auth" in msg
        assert "X-API-Key" in msg

    def test_to_response(self):
        err = AuthRequiredError(
            scheme_info="Bearer token auth",
            detail="Pass your token via Authorization header.",
        )
        resp = err.to_response()
        assert resp["type"] == "AuthRequiredError"
        assert resp["scheme"] == "Bearer token auth"
        assert "Authorization" in resp["detail"]

    def test_to_response_no_detail(self):
        err = AuthRequiredError(scheme_info="OAuth2 auth")
        resp = err.to_response()
        assert "detail" not in resp

    def test_is_a2a_lite_error(self):
        err = AuthRequiredError()
        assert isinstance(err, A2ALiteError)
