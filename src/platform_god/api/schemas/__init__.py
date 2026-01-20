"""
Pydantic schemas for API request/response validation.

This module exports all request and response schemas used by the API.
"""

from platform_god.api.schemas.exceptions import (
    APIException,
    ConflictError,
    InternalError,
    NotFoundError,
    PreconditionFailedError,
    ServiceUnavailableError,
    ValidationError,
)
from platform_god.api.schemas.requests import (
    AgentExecuteRequest,
    AgentListRequest,
    ChainCancelRequest,
    ChainExecuteRequest,
    ChainType,
    ExecutionMode,
    RegistryEntityRequest,
    RegistryQueryRequest,
    RegistryUpdateRequest,
    RunListRequest,
)
from platform_god.api.schemas.responses import (
    AgentClass,
    AgentExecuteResponse,
    AgentExecutionResult,
    AgentListResponse,
    AgentPermissionLevel,
    AgentResponse,
    AgentStatus,
    ChainExecuteResponse,
    ChainListResponse,
    ChainStopReason,
    ChainStepResponse,
    ChainTypeInfo,
    ErrorResponse,
    HealthResponse,
    RegistryEntityResponse,
    RegistryListResponse,
    RegistryOperationResponse,
    RunDetail,
    RunListResponse,
    RunStatus,
    RunSummary,
)

__all__ = [
    # Exceptions
    "APIException",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "PreconditionFailedError",
    "InternalError",
    "ServiceUnavailableError",
    # Requests
    "AgentListRequest",
    "AgentExecuteRequest",
    "ChainExecuteRequest",
    "ChainCancelRequest",
    "ChainType",
    "ExecutionMode",
    "RunListRequest",
    "RegistryEntityRequest",
    "RegistryUpdateRequest",
    "RegistryQueryRequest",
    # Responses
    "AgentResponse",
    "AgentListResponse",
    "AgentExecutionResult",
    "AgentExecuteResponse",
    "AgentClass",
    "AgentStatus",
    "AgentPermissionLevel",
    "ChainTypeInfo",
    "ChainListResponse",
    "ChainExecuteResponse",
    "ChainStepResponse",
    "ChainStopReason",
    "RunSummary",
    "RunDetail",
    "RunListResponse",
    "RunStatus",
    "RegistryEntityResponse",
    "RegistryListResponse",
    "RegistryOperationResponse",
    "HealthResponse",
    "ErrorResponse",
]
