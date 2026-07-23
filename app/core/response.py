"""Standard success/error response envelope."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    message: str
    error_code: str
    data: None = None


def success_response(data: object = None, message: str = "OK") -> dict:
    """Build a success envelope dict."""
    return {"success": True, "message": message, "data": data}


def error_response(message: str, error_code: str, data: object = None) -> dict:
    """Build an error envelope dict."""
    return {"success": False, "message": message, "error_code": error_code, "data": data}
