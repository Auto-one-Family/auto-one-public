"""
Standardisiertes API Response Format

Paket X: Code Consolidation & Industrial Quality
Alle API-Endpoints verwenden dieses einheitliche Response-Format.
"""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Standardisiertes API Response Format für alle Endpoints.

    Beispiel:
        {
            "success": true,
            "data": {"esp_id": "ESP_001", "status": "online"},
            "message": "Operation completed successfully"
        }
    """

    success: bool = Field(..., description="Whether the operation was successful")
    data: Optional[T] = Field(None, description="Response data (if any)")
    message: Optional[str] = Field(None, description="Optional human-readable message")
    errors: Optional[List[str]] = Field(
        None, description="List of error messages (if success=false)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {"esp_id": "ESP_001"},
                "message": "Operation completed successfully",
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standardisiertes paginiertes Response Format.

    Beispiel:
        {
            "success": true,
            "data": [...],
            "total": 100,
            "page": 1,
            "page_size": 20,
            "has_more": true
        }
    """

    success: bool = Field(True, description="Whether the operation was successful")
    data: List[T] = Field(..., description="List of items for current page")
    total: int = Field(..., ge=0, description="Total number of items")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    has_more: bool = Field(..., description="Whether there are more pages")

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.page_size - 1) // self.page_size

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": [{"esp_id": "ESP_001"}],
                "total": 100,
                "page": 1,
                "page_size": 20,
                "has_more": True,
            }
        }
