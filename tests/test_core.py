from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, AppException
from app.core.response import success_response, error_response


def test_settings_load():
    s = get_settings()
    assert s.api_v1_prefix == "/api/v1"
    assert isinstance(s.cors_origins, list)


def test_cors_origins_parses_comma_string(monkeypatch):
    """A plain comma-separated CORS_ORIGINS env value must not be JSON-decoded."""
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_not_found_is_app_exception():
    err = NotFoundError("resident not found")
    assert isinstance(err, AppException)
    assert err.status_code == 404
    assert err.error_code == "NOT_FOUND"


def test_envelope_helpers():
    ok = success_response({"id": 1}, "done")
    assert ok == {"success": True, "message": "done", "data": {"id": 1}}
    bad = error_response("nope", "NOT_FOUND")
    assert bad == {"success": False, "message": "nope", "error_code": "NOT_FOUND", "data": None}
