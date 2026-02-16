"""Error handling utilities for OpenHAB Semantic MCP."""

import logging
from typing import Any, Dict

from ..exceptions import OpenHABSemanticMCPError


def handle_error(
    logger: logging.Logger, operation: str, error: Exception
) -> Dict[str, Any]:
    """Standardized error handling for MCP tools.

    Args:
        logger: Logger instance
        operation: Name of the operation that failed
        error: Exception that occurred

    Returns:
        Standardized error response dictionary
    """
    if isinstance(error, OpenHABSemanticMCPError):
        # Custom exception - use structured data
        logger.error(f"Error in {operation}: {error.message}")
        error_response = error.to_dict()
        error_response["success"] = False
        return error_response
    else:
        # Generic exception - create basic response
        logger.error(f"Unexpected error in {operation}: {error}")
        return {
            "success": False,
            "error_type": error.__class__.__name__,
            "message": str(error),
            "details": {},
        }


def create_error_response(error: Exception, operation: str = "") -> Dict[str, Any]:
    """Create standardized error response from exception.

    Args:
        error: Exception that occurred
        operation: Optional operation context

    Returns:
        Standardized error response dictionary
    """
    if isinstance(error, OpenHABSemanticMCPError):
        response = error.to_dict()
    else:
        response = {
            "error_type": error.__class__.__name__,
            "error_code": None,
            "message": str(error),
            "details": {},
        }

    response["success"] = False
    if operation:
        response["operation"] = operation

    return response
