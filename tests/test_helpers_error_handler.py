"""Tests for helper error handling utilities."""

from unittest.mock import Mock

from openhab_semantic_mcp.exceptions import InvalidFilterError
from openhab_semantic_mcp.helpers.error_handler import create_error_response, handle_error


def test_handle_error_with_custom_exception():
    logger = Mock()
    error = InvalidFilterError(
        filter_name="location",
        filter_value="UnknownRoom",
        reason="Filter value does not exist",
    )

    response = handle_error(logger, "find_items", error)

    assert response["success"] is False
    assert response["error_type"] == "InvalidFilterError"
    assert response["error_code"] == "INVALID_FILTER"
    logger.error.assert_called_once()


def test_handle_error_with_generic_exception():
    logger = Mock()
    error = ValueError("bad input")

    response = handle_error(logger, "find_items", error)

    assert response == {
        "success": False,
        "error_type": "ValueError",
        "message": "bad input",
        "details": {},
    }
    logger.error.assert_called_once()


def test_create_error_response_with_custom_exception_and_operation():
    error = InvalidFilterError(
        filter_name="equipment",
        filter_value="UnknownDevice",
        reason="Filter value does not exist",
    )

    response = create_error_response(error, operation="search")

    assert response["success"] is False
    assert response["operation"] == "search"
    assert response["error_type"] == "InvalidFilterError"
    assert response["error_code"] == "INVALID_FILTER"


def test_create_error_response_with_generic_exception_without_operation():
    response = create_error_response(RuntimeError("unexpected"))

    assert response == {
        "success": False,
        "error_type": "RuntimeError",
        "error_code": None,
        "message": "unexpected",
        "details": {},
    }
