"""
Common Pydantic Schemas - Shared Base Classes and Response Models

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- Base response models for consistent API responses
- Paginated response wrapper for list endpoints
- Common mixins for timestamps and IDs
- Standard error response format
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Type variable for generic responses
T = TypeVar("T")


# =============================================================================
# Base Mixins
# =============================================================================


class TimestampMixin(BaseModel):
    """Mixin for models with created_at and updated_at timestamps."""

    created_at: Optional[datetime] = Field(
        None,
        description="Record creation timestamp",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Record last update timestamp",
    )


class IDMixin(BaseModel):
    """Mixin for models with an ID field."""

    id: int = Field(
        ...,
        description="Unique identifier",
        ge=1,
    )


# =============================================================================
# Base Response Models
# =============================================================================


class BaseResponse(BaseModel):
    """
    Base response model for all API responses.

    Provides consistent structure with success flag and optional message.
    """

    success: bool = Field(
        True,
        description="Whether the operation succeeded",
    )
    message: Optional[str] = Field(
        None,
        description="Optional human-readable message",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {"success": True, "message": "Operation completed successfully"}
        },
    )


class ErrorResponse(BaseModel):
    """
    Standard error response model.

    Used for 4xx and 5xx HTTP responses with consistent error format.
    """

    success: bool = Field(
        False,
        description="Always False for error responses",
    )
    error: str = Field(
        ...,
        description="Error type or code (e.g., 'VALIDATION_ERROR', 'NOT_FOUND')",
    )
    detail: str = Field(
        ...,
        description="Human-readable error description",
    )
    timestamp: Optional[int] = Field(
        None,
        description="Error timestamp (Unix seconds)",
    )
    path: Optional[str] = Field(
        None,
        description="Request path that caused the error",
    )
    request_id: Optional[str] = Field(
        None,
        description="Request ID for tracing",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "NOT_FOUND",
                "detail": "ESP device 'ESP_12AB34CD' not found",
                "timestamp": 1735818000,
                "path": "/api/v1/esp/devices/ESP_12AB34CD",
                "request_id": "req-abc123",
            }
        }
    )


class DataResponse(BaseResponse, Generic[T]):
    """
    Generic data response wrapper.

    Wraps a single data object in a consistent response structure.
    """

    data: Optional[T] = Field(
        None,
        description="Response data payload",
    )


class ListResponse(BaseResponse, Generic[T]):
    """
    Generic list response wrapper.

    Wraps a list of items in a consistent response structure.
    """

    data: List[T] = Field(
        default_factory=list,
        description="List of items",
    )
    count: int = Field(
        0,
        description="Number of items in the list",
        ge=0,
    )


# =============================================================================
# Pagination
# =============================================================================


class PaginationParams(BaseModel):
    """
    Pagination query parameters.

    Used as dependency for paginated list endpoints.
    """

    page: int = Field(
        1,
        description="Page number (1-indexed)",
        ge=1,
    )
    page_size: int = Field(
        20,
        description="Items per page",
        ge=1,
        le=100,
    )

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size."""
        return self.page_size


class PaginationMeta(BaseModel):
    """Pagination metadata for paginated responses."""

    page: int = Field(
        ...,
        description="Current page number",
        ge=1,
    )
    page_size: int = Field(
        ...,
        description="Items per page",
        ge=1,
    )
    total_items: int = Field(
        ...,
        description="Total number of items across all pages",
        ge=0,
    )
    total_pages: int = Field(
        ...,
        description="Total number of pages",
        ge=0,
    )
    has_next: bool = Field(
        ...,
        description="Whether there is a next page",
    )
    has_prev: bool = Field(
        ...,
        description="Whether there is a previous page",
    )

    @classmethod
    def from_pagination(
        cls,
        page: int,
        page_size: int,
        total_items: int,
    ) -> "PaginationMeta":
        """Create PaginationMeta from pagination parameters."""
        total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class PaginatedResponse(BaseResponse, Generic[T]):
    """
    Paginated response wrapper for list endpoints.

    Includes pagination metadata alongside the data items.
    """

    data: List[T] = Field(
        default_factory=list,
        description="List of items for current page",
    )
    pagination: PaginationMeta = Field(
        ...,
        description="Pagination metadata",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": None,
                "data": [],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total_items": 100,
                    "total_pages": 5,
                    "has_next": True,
                    "has_prev": False,
                },
            }
        }
    )


# =============================================================================
# Filter/Sort Parameters
# =============================================================================


class SortOrder(BaseModel):
    """Sort order specification."""

    field: str = Field(
        ...,
        description="Field name to sort by",
    )
    direction: str = Field(
        "asc",
        description="Sort direction: 'asc' or 'desc'",
        pattern="^(asc|desc)$",
    )


class TimeRangeFilter(BaseModel):
    """Time range filter for queries."""

    start: Optional[datetime] = Field(
        None,
        description="Start of time range (inclusive)",
    )
    end: Optional[datetime] = Field(
        None,
        description="End of time range (inclusive)",
    )


class TimeRangeFilterUnix(BaseModel):
    """Time range filter using Unix timestamps."""

    start_ts: Optional[int] = Field(
        None,
        description="Start timestamp (Unix seconds)",
        ge=0,
    )
    end_ts: Optional[int] = Field(
        None,
        description="End timestamp (Unix seconds)",
        ge=0,
    )


# =============================================================================
# Status Response
# =============================================================================


class StatusResponse(BaseResponse):
    """
    Simple status response for operations.

    Used for endpoints that perform actions without returning data.
    """

    action: str = Field(
        ...,
        description="Action that was performed",
    )
    target: Optional[str] = Field(
        None,
        description="Target of the action (e.g., device ID)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Device restarted successfully",
                "action": "restart",
                "target": "ESP_12AB34CD",
            }
        }
    )


# =============================================================================
# Validation Helpers
# =============================================================================


class ValidationError(BaseModel):
    """Single validation error detail."""

    loc: List[str] = Field(
        ...,
        description="Location of the error (field path)",
    )
    msg: str = Field(
        ...,
        description="Error message",
    )
    type: str = Field(
        ...,
        description="Error type",
    )


class ValidationErrorResponse(ErrorResponse):
    """
    Validation error response with field-level details.

    Used for 422 Unprocessable Entity responses.
    """

    error: str = Field(
        "VALIDATION_ERROR",
        description="Error type",
    )
    errors: List[ValidationError] = Field(
        default_factory=list,
        description="List of validation errors",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "VALIDATION_ERROR",
                "detail": "Request validation failed",
                "errors": [
                    {
                        "loc": ["body", "gpio"],
                        "msg": "ensure this value is less than or equal to 39",
                        "type": "value_error.number.not_le",
                    }
                ],
            }
        }
    )
