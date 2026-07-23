from app.core.config import get_settings
from app.core.exceptions import NotFoundError, AppException
from app.core.response import success_response, error_response


def test_settings_load():
    s = get_settings()
    assert s.api_v1_prefix == "/api/v1"
    assert isinstance(s.cors_origins, list)


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
