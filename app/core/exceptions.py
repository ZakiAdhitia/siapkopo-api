"""Custom application exceptions mapped to the error envelope."""


class AppException(Exception):
    """Base application error carrying an envelope-friendly payload."""

    def __init__(self, message: str, error_code: str = "ERROR", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, "NOT_FOUND", 404)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, "FORBIDDEN", 403)


class ConflictError(AppException):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message, "CONFLICT", 409)


class ValidationAppError(AppException):
    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, "VALIDATION_ERROR", 422)
