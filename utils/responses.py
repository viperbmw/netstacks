"""
Standardized API Response Helpers

Provides consistent response formatting across all API endpoints.
"""

from flask import jsonify
from typing import Any, Dict, List, Optional, Union


def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200
) -> tuple:
    """
    Create a successful API response.

    Args:
        data: Response data (dict, list, or any JSON-serializable object)
        message: Optional success message
        status_code: HTTP status code (default 200)

    Returns:
        tuple: (response, status_code)

    Example:
        return success_response({'user': user_data}, 'User created', 201)
    """
    response = {'success': True}

    if data is not None:
        response['data'] = data

    if message:
        response['message'] = message

    return jsonify(response), status_code


def error_response(
    message: str,
    status_code: int = 400,
    error_code: Optional[str] = None,
    details: Optional[Dict] = None
) -> tuple:
    """
    Create an error API response.

    Args:
        message: Error message
        status_code: HTTP status code (default 400)
        error_code: Optional error code for programmatic handling
        details: Optional additional error details

    Returns:
        tuple: (response, status_code)

    Example:
        return error_response('User not found', 404, 'USER_NOT_FOUND')
    """
    response = {
        'success': False,
        'error': message
    }

    if error_code:
        response['error_code'] = error_code

    if details:
        response['details'] = details

    return jsonify(response), status_code


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    per_page: int = 20,
    message: Optional[str] = None
) -> tuple:
    """
    Create a paginated API response.

    Args:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number
        per_page: Items per page
        message: Optional message

    Returns:
        tuple: (response, status_code)

    Example:
        return paginated_response(users, total_count, page=2, per_page=25)
    """
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    response = {
        'success': True,
        'data': items,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    }

    if message:
        response['message'] = message

    return jsonify(response), 200


def validation_error_response(errors: Dict[str, List[str]]) -> tuple:
    """
    Create a validation error response with field-specific errors.

    Args:
        errors: Dict mapping field names to list of error messages

    Returns:
        tuple: (response, status_code)

    Example:
        return validation_error_response({
            'email': ['Invalid email format'],
            'password': ['Password too short', 'Must contain a number']
        })
    """
    return error_response(
        message='Validation failed',
        status_code=400,
        error_code='VALIDATION_ERROR',
        details={'fields': errors}
    )
