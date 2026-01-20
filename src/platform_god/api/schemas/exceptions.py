"""
Exception classes for API error handling.
"""



class APIException(Exception):
    """
    Base exception for API errors.

    All API exceptions should inherit from this class to ensure
    consistent error response formatting.
    """

    status_code: int = 500
    error_type: str = "api_error"
    message: str = "An error occurred"
    detail: str | None = None

    def __init__(
        self,
        message: str | None = None,
        detail: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class ValidationError(APIException):
    """Exception raised when request validation fails."""

    status_code = 400
    error_type = "validation_error"
    message = "Request validation failed"

    def __init__(self, fields: dict[str, str]) -> None:
        self.fields = fields
        super().__init__(message=f"Validation failed for {len(fields)} field(s)")


class NotFoundError(APIException):
    """Exception raised when a requested resource is not found."""

    status_code = 404
    error_type = "not_found"
    message = "Resource not found"


class ConflictError(APIException):
    """Exception raised when a request conflicts with existing state."""

    status_code = 409
    error_type = "conflict"
    message = "Resource already exists or state conflict"


class PreconditionFailedError(APIException):
    """Exception raised when a precondition for the operation fails."""

    status_code = 412
    error_type = "precondition_failed"
    message = "Precondition failed"


class InternalError(APIException):
    """Exception raised for internal server errors."""

    status_code = 500
    error_type = "internal_error"
    message = "Internal server error"


class ServiceUnavailableError(APIException):
    """Exception raised when a required service is unavailable."""

    status_code = 503
    error_type = "service_unavailable"
    message = "Service temporarily unavailable"
