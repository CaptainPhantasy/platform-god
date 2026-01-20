"""
Platform God Exception Hierarchy.

Defines all custom exceptions used across the Platform God system.
Provides consistent error handling and debugging information.
"""

from typing import Any


class PlatformGodError(Exception):
    """
    Base exception for all Platform God errors.

    All custom exceptions inherit from this class, allowing
    generic catch blocks and consistent error handling.
    """

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        """
        Initialize a PlatformGodError.

        Args:
            message: Human-readable error message
            details: Optional structured data for debugging
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation with details."""
        base = self.message
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{base} ({details_str})"
        return base

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class AgentExecutionError(PlatformGodError):
    """
    Errors during agent execution.

    Raised when an agent fails to execute properly, including:
    - Precheck validation failures
    - Scope violations
    - Execution timeouts
    - Output validation failures
    """

    def __init__(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        agent_class: str | None = None,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize an AgentExecutionError.

        Args:
            message: Human-readable error message
            agent_name: Name of the agent that failed
            agent_class: Class of the agent that failed
            stage: Execution stage where error occurred
            details: Optional structured data for debugging
        """
        details = details or {}
        if agent_name:
            details["agent_name"] = agent_name
        if agent_class:
            details["agent_class"] = agent_class
        if stage:
            details["stage"] = stage

        super().__init__(message, details=details)
        self.agent_name = agent_name
        self.agent_class = agent_class
        self.stage = stage


class PrecheckError(AgentExecutionError):
    """
    Raised when agent precheck validation fails.

    Prechecks validate that required inputs are present and
    the execution environment is valid before running.
    """

    def __init__(
        self,
        message: str,
        *,
        failures: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize a PrecheckError.

        Args:
            message: Human-readable error message
            failures: List of specific validation failures
            **kwargs: Additional arguments passed to AgentExecutionError
        """
        details = kwargs.pop("details", {}) or {}
        if failures:
            details["failures"] = failures
        kwargs["details"] = details

        super().__init__(message, stage="precheck", **kwargs)
        self.failures = failures or []


class ScopeViolationError(AgentExecutionError):
    """
    Raised when an agent attempts to access resources outside its scope.

    This security-critical error prevents unauthorized access
    to files, paths, or resources.
    """

    def __init__(
        self,
        message: str,
        *,
        requested_path: str | None = None,
        allowed_paths: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize a ScopeViolationError.

        Args:
            message: Human-readable error message
            requested_path: The path that was requested
            allowed_paths: List of paths the agent is allowed to access
            **kwargs: Additional arguments passed to AgentExecutionError
        """
        details = kwargs.pop("details", {}) or {}
        if requested_path:
            details["requested_path"] = requested_path
        if allowed_paths:
            details["allowed_paths"] = allowed_paths
        kwargs["details"] = details

        super().__init__(message, stage="scope_check", **kwargs)
        self.requested_path = requested_path
        self.allowed_paths = allowed_paths or []


class AgentNotFoundError(PlatformGodError):
    """
    Raised when an agent is not found in the registry.

    This occurs when attempting to execute an agent that
    has not been registered or does not exist.
    """

    def __init__(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize an AgentNotFoundError.

        Args:
            message: Human-readable error message
            agent_name: Name of the agent that was not found
            details: Optional structured data for debugging
        """
        details = details or {}
        if agent_name:
            details["agent_name"] = agent_name

        super().__init__(message, details=details)
        self.agent_name = agent_name


class RegistryError(PlatformGodError):
    """
    Errors in registry operations.

    Raised when registry storage operations fail, including:
    - Entity not found
    - Entity already exists
    - Checksum mismatches
    - Index corruption
    """

    def __init__(
        self,
        message: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize a RegistryError.

        Args:
            message: Human-readable error message
            entity_type: Type of entity involved
            entity_id: ID of entity involved
            operation: Operation being performed
            details: Optional structured data for debugging
        """
        details = details or {}
        if entity_type:
            details["entity_type"] = entity_type
        if entity_id:
            details["entity_id"] = entity_id
        if operation:
            details["operation"] = operation

        super().__init__(message, details=details)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.operation = operation


class EntityNotFoundError(RegistryError):
    """Raised when a requested entity does not exist in the registry."""

    def __init__(
        self,
        message: str = "Entity not found",
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ):
        super().__init__(
            message,
            entity_type=entity_type,
            entity_id=entity_id,
            operation="read",
        )


class EntityExistsError(RegistryError):
    """Raised when attempting to create an entity that already exists."""

    def __init__(
        self,
        message: str = "Entity already exists",
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ):
        super().__init__(
            message,
            entity_type=entity_type,
            entity_id=entity_id,
            operation="register",
        )


class ChecksumMismatchError(RegistryError):
    """Raised when entity checksum does not match the stored index."""

    def __init__(
        self,
        message: str = "Checksum mismatch",
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ):
        details = {"expected": expected, "actual": actual}
        super().__init__(
            message,
            entity_type=entity_type,
            entity_id=entity_id,
            operation="verify",
            details=details,
        )
        self.expected = expected
        self.actual = actual


class ConfigurationError(PlatformGodError):
    """
    Errors in configuration loading or validation.

    Raised when:
    - Configuration files are missing or malformed
    - Required environment variables are not set
    - Configuration values are invalid
    """

    def __init__(
        self,
        message: str,
        *,
        config_file: str | None = None,
        env_var: str | None = None,
        config_key: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize a ConfigurationError.

        Args:
            message: Human-readable error message
            config_file: Path to configuration file if applicable
            env_var: Environment variable name if applicable
            config_key: Configuration key if applicable
            details: Optional structured data for debugging
        """
        details = details or {}
        if config_file:
            details["config_file"] = config_file
        if env_var:
            details["env_var"] = env_var
        if config_key:
            details["config_key"] = config_key

        super().__init__(message, details=details)
        self.config_file = config_file
        self.env_var = env_var
        self.config_key = config_key


class ValidationError(PlatformGodError):
    """
    Errors during data validation.

    Raised when:
    - Input data fails schema validation
    - Output data does not match expected format
    - Required fields are missing
    - Data type constraints are violated
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        expected_type: str | None = None,
        actual_type: str | None = None,
        validation_errors: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize a ValidationError.

        Args:
            message: Human-readable error message
            field: Field name that failed validation
            expected_type: Expected type or format
            actual_type: Actual type received
            validation_errors: List of specific validation errors
            details: Optional structured data for debugging
        """
        details = details or {}
        if field:
            details["field"] = field
        if expected_type:
            details["expected_type"] = expected_type
        if actual_type:
            details["actual_type"] = actual_type
        if validation_errors:
            details["validation_errors"] = validation_errors

        super().__init__(message, details=details)
        self.field = field
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.validation_errors = validation_errors or []


class LLMError(PlatformGodError):
    """
    Errors from LLM provider interactions.

    Raised when:
    - API calls fail
    - Authentication fails
    - Rate limits are exceeded
    - Responses cannot be parsed
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
        retry_attempt: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize an LLMError.

        Args:
            message: Human-readable error message
            provider: LLM provider name
            model: Model being used
            status_code: HTTP status code if applicable
            retry_attempt: Retry attempt number if applicable
            details: Optional structured data for debugging
        """
        details = details or {}
        if provider:
            details["provider"] = provider
        if model:
            details["model"] = model
        if status_code:
            details["status_code"] = status_code
        if retry_attempt is not None:
            details["retry_attempt"] = retry_attempt

        super().__init__(message, details=details)
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.retry_attempt = retry_attempt


class LLMAuthenticationError(LLMError):
    """Raised when LLM API authentication fails."""

    def __init__(
        self,
        message: str = "API authentication failed",
        *,
        provider: str | None = None,
    ):
        super().__init__(message, provider=provider, status_code=401)


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        provider: str | None = None,
        retry_after: int | None = None,
    ):
        details = {}
        if retry_after is not None:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, provider=provider, status_code=429, details=details)
        self.retry_after = retry_after


class LLMParseError(LLMError):
    """Raised when LLM response cannot be parsed as expected format."""

    def __init__(
        self,
        message: str = "Failed to parse LLM response",
        *,
        response_preview: str | None = None,
        expected_format: str | None = None,
    ):
        details = {}
        if response_preview:
            details["response_preview"] = response_preview[:200]
        if expected_format:
            details["expected_format"] = expected_format
        super().__init__(message, details=details)
        self.response_preview = response_preview
        self.expected_format = expected_format


class ChainExecutionError(PlatformGodError):
    """
    Errors during chain execution in orchestrator.

    Raised when:
    - Chain step fails
    - State passing fails
    - Chain definition is invalid
    - Stop conditions are triggered
    """

    def __init__(
        self,
        message: str,
        *,
        chain_name: str | None = None,
        step_index: int | None = None,
        agent_name: str | None = None,
        stop_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize a ChainExecutionError.

        Args:
            message: Human-readable error message
            chain_name: Name of the chain being executed
            step_index: Index of the step that failed
            agent_name: Name of the agent that failed
            stop_reason: Reason for chain stopping
            details: Optional structured data for debugging
        """
        details = details or {}
        if chain_name:
            details["chain_name"] = chain_name
        if step_index is not None:
            details["step_index"] = step_index
        if agent_name:
            details["agent_name"] = agent_name
        if stop_reason:
            details["stop_reason"] = stop_reason

        super().__init__(message, details=details)
        self.chain_name = chain_name
        self.step_index = step_index
        self.agent_name = agent_name
        self.stop_reason = stop_reason


def format_exception(error: Exception) -> str:
    """
    Format an exception for user-friendly display.

    Args:
        error: The exception to format

    Returns:
        Formatted error message string
    """
    if isinstance(error, PlatformGodError):
        return str(error)
    return f"{error.__class__.__name__}: {error}"


def is_retriable_error(error: Exception) -> bool:
    """
    Determine if an error is suitable for retry.

    Args:
        error: The exception to check

    Returns:
        True if the error should be retried
    """
    if isinstance(error, LLMRateLimitError):
        return True
    if isinstance(error, LLMError):
        # Retry on server errors and connection issues
        if error.status_code and error.status_code >= 500:
            return True
        if error.status_code in (429, 502, 503, 504):
            return True
    return False
