"""Custom exceptions for OpenHAB Semantic MCP.

This module provides a hierarchy of custom exceptions for better error handling,
debugging, and user experience.
"""

from typing import Optional, Any, Dict


class OpenHABSemanticMCPError(Exception):
    """Base exception for OpenHAB Semantic MCP."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# OpenHAB Client Errors
# =============================================================================


class OpenHABError(OpenHABSemanticMCPError):
    """Base OpenHAB client error."""

    pass


class OpenHABConnectionError(OpenHABError):
    """Connection to OpenHAB failed."""

    def __init__(
        self, message: str, url: Optional[str] = None, retry_after: Optional[int] = None
    ):
        super().__init__(message, "OPENHAB_CONNECTION_ERROR")
        self.url = url
        self.retry_after = retry_after
        self.details.update({"url": url, "retry_after": retry_after})


class OpenHABTimeoutError(OpenHABError):
    """OpenHAB operation timed out."""

    def __init__(self, message: str, timeout_seconds: Optional[int] = None):
        super().__init__(message, "OPENHAB_TIMEOUT_ERROR")
        self.timeout_seconds = timeout_seconds
        self.details.update({"timeout_seconds": timeout_seconds})


class OpenHABAuthenticationError(OpenHABError):
    """OpenHAB authentication failed."""

    def __init__(self, message: str, auth_type: Optional[str] = None):
        super().__init__(message, "OPENHAB_AUTH_ERROR")
        self.auth_type = auth_type
        self.details.update({"auth_type": auth_type})


class ItemNotFoundError(OpenHABError):
    """Item not found in OpenHAB."""

    def __init__(self, item_name: str):
        super().__init__(f"Item '{item_name}' not found", "ITEM_NOT_FOUND")
        self.item_name = item_name
        self.details.update({"item_name": item_name})


class ItemCommandError(OpenHABError):
    """Failed to send command to item."""

    def __init__(self, item_name: str, command: str, reason: str):
        super().__init__(
            f"Failed to send command '{command}' to item '{item_name}': {reason}",
            "ITEM_COMMAND_ERROR",
        )
        self.item_name = item_name
        self.command = command
        self.reason = reason
        self.details.update(
            {"item_name": item_name, "command": command, "reason": reason}
        )


class ItemStateError(OpenHABError):
    """Failed to update item state."""

    def __init__(self, item_name: str, state: str, reason: str):
        super().__init__(
            f"Failed to update state '{state}' for item '{item_name}': {reason}",
            "ITEM_STATE_ERROR",
        )
        self.item_name = item_name
        self.state = state
        self.reason = reason
        self.details.update({"item_name": item_name, "state": state, "reason": reason})


class SSEConnectionError(OpenHABError):
    """Server-Sent Events connection failed."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, "SSE_CONNECTION_ERROR")
        self.retry_after = retry_after
        self.details.update({"retry_after": retry_after})


# =============================================================================
# Inventory Errors
# =============================================================================


class InventoryError(OpenHABSemanticMCPError):
    """Base inventory error."""

    pass


class InvalidFilterError(InventoryError):
    """Invalid filter specification."""

    def __init__(
        self,
        filter_name: str,
        filter_value: Any,
        reason: str,
        guidance: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            f"Invalid filter '{filter_name}' with value '{filter_value}': {reason}",
            "INVALID_FILTER",
        )
        self.filter_name = filter_name
        self.filter_value = filter_value
        self.reason = reason
        self.guidance = guidance or {}
        self.details.update(
            {
                "filter_name": filter_name,
                "filter_value": str(filter_value),
                "reason": reason,
                "guidance": self.guidance,
            }
        )


class SemanticHierarchyError(InventoryError):
    """Error in semantic hierarchy processing."""

    def __init__(self, message: str, hierarchy_type: Optional[str] = None):
        super().__init__(message, "SEMANTIC_HIERARCHY_ERROR")
        self.hierarchy_type = hierarchy_type
        self.details.update({"hierarchy_type": hierarchy_type})


# =============================================================================
# Monitoring Errors
# =============================================================================


class MonitoringError(OpenHABSemanticMCPError):
    """Base monitoring error."""

    pass


class InvalidMonitoringTaskError(MonitoringError):
    """Invalid monitoring task configuration."""

    def __init__(self, task_id: str, reason: str):
        super().__init__(
            f"Invalid monitoring task '{task_id}': {reason}", "INVALID_MONITORING_TASK"
        )
        self.task_id = task_id
        self.reason = reason
        self.details.update({"task_id": task_id, "reason": reason})


class TriggerEvaluationError(MonitoringError):
    """Error during trigger evaluation."""

    def __init__(self, task_id: str, item_name: str, reason: str):
        super().__init__(
            f"Trigger evaluation failed for task '{task_id}' on item '{item_name}': {reason}",
            "TRIGGER_EVALUATION_ERROR",
        )
        self.task_id = task_id
        self.item_name = item_name
        self.reason = reason
        self.details.update(
            {"task_id": task_id, "item_name": item_name, "reason": reason}
        )


class MonitoringConfigurationError(MonitoringError):
    """Monitoring configuration error."""

    def __init__(self, config_key: str, config_value: Any, reason: str):
        super().__init__(
            f"Invalid monitoring configuration '{config_key}' = '{config_value}': {reason}",
            "MONITORING_CONFIG_ERROR",
        )
        self.config_key = config_key
        self.config_value = config_value
        self.reason = reason
        self.details.update(
            {
                "config_key": config_key,
                "config_value": str(config_value),
                "reason": reason,
            }
        )


class WebhookError(MonitoringError):
    """Webhook delivery failed."""

    def __init__(
        self,
        task_id: str,
        webhook_url: str,
        status_code: Optional[int] = None,
        reason: str = "",
    ):
        super().__init__(
            f"Webhook delivery failed for task '{task_id}' to '{webhook_url}': {reason}",
            "WEBHOOK_ERROR",
        )
        self.task_id = task_id
        self.webhook_url = webhook_url
        self.status_code = status_code
        self.reason = reason
        self.details.update(
            {
                "task_id": task_id,
                "webhook_url": webhook_url,
                "status_code": status_code,
                "reason": reason,
            }
        )


# =============================================================================
# Storage Backend Errors
# =============================================================================


class StorageError(OpenHABSemanticMCPError):
    """Base storage error."""

    pass


class StorageConnectionError(StorageError):
    """Storage backend connection failed."""

    def __init__(self, backend_name: str, reason: str):
        super().__init__(
            f"Storage backend '{backend_name}' connection failed: {reason}",
            "STORAGE_CONNECTION_ERROR",
        )
        self.backend_name = backend_name
        self.reason = reason
        self.details.update({"backend_name": backend_name, "reason": reason})


# =============================================================================
# MCP Server Errors
# =============================================================================


class MCPServerError(OpenHABSemanticMCPError):
    """Base MCP server error."""

    pass


class ToolExecutionError(MCPServerError):
    """Tool execution failed."""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Tool '{tool_name}' execution failed: {reason}", "TOOL_EXECUTION_ERROR"
        )
        self.tool_name = tool_name
        self.reason = reason
        self.details.update({"tool_name": tool_name, "reason": reason})


class ValidationError(MCPServerError):
    """Input validation failed."""

    def __init__(self, field_name: str, field_value: Any, reason: str):
        super().__init__(
            f"Validation failed for field '{field_name}' with value '{field_value}': {reason}",
            "VALIDATION_ERROR",
        )
        self.field_name = field_name
        self.field_value = field_value
        self.reason = reason
        self.details.update(
            {
                "field_name": field_name,
                "field_value": str(field_value),
                "reason": reason,
            }
        )
