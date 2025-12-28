"""
Standardized API Response Utilities for NetStacks

Provides consistent response formatting across all microservices.
"""

from typing import Any, Dict, List, Optional, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar('T')


class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper.

    Attributes:
        success: Whether the operation was successful
        data: The response data (if successful)
        error: Error message (if failed)
        message: Optional status message
    """
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    message: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated API response wrapper.

    Attributes:
        success: Whether the operation was successful
        data: List of items
        total: Total number of items
        page: Current page number (1-indexed)
        page_size: Number of items per page
        total_pages: Total number of pages
    """
    success: bool = True
    data: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def success_response(
    data: Any = None,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized success response.

    Args:
        data: The response data
        message: Optional success message

    Returns:
        Dict with success response structure
    """
    response = {
        "success": True,
        "data": data,
    }
    if message:
        response["message"] = message
    return response


def error_response(
    error: str,
    data: Any = None
) -> Dict[str, Any]:
    """
    Create a standardized error response.

    Args:
        error: Error message
        data: Optional additional error data

    Returns:
        Dict with error response structure
    """
    response = {
        "success": False,
        "error": error,
    }
    if data is not None:
        response["data"] = data
    return response


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """
    Create a standardized paginated response.

    Args:
        items: List of items for this page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dict with paginated response structure
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    return {
        "success": True,
        "data": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def list_response(items: List[Any]) -> Dict[str, Any]:
    """
    Create a simple list response without pagination.

    Args:
        items: List of items

    Returns:
        Dict with list response structure
    """
    return {
        "success": True,
        "data": items,
        "total": len(items),
    }
