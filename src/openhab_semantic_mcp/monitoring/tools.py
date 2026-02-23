"""MCP tool registration for monitoring functionality."""

from datetime import datetime
import logging
import os
from typing import Any, Dict, Optional

from pydantic import Field

from ..search.models import ItemRefinement, SearchFilters
from ..search.descriptions import (
    FILTERS_DESCRIPTION_MONITORING,
    REFINEMENT_DESCRIPTION,
)
from ..config import MonitoringConfig
from .factory import create_monitoring_storage
from .service import MonitoringService
from .models import (
    MonitoringMode,
    MonitoringTask,
    MonitoringIntent,
    TaskUpdate,
    ensure_timezone_aware,
    get_timezone_aware_datetime,
)

logger = logging.getLogger(__name__)

def get_description():
    timezone = os.environ.get("MONITORING_TIMEZONE", "UTC")
    return f"""Create a monitoring task with flexible modes and time-based scheduling.

        Creates monitoring tasks that watch OpenHAB items for state changes and
        trigger webhooks when conditions are met. Supports both one-shot and
        time-window monitoring modes.

        ⚠️ **IMPORTANT**: All times are interpreted in {timezone} timezone unless
        explicitly specified with timezone offset (e.g., '2026-02-10T14:48:00+01:00').

        **Parameters:**
        - **mode**: 'one_shot' (triggers once then completes) or 'time_window' (monitors for duration)
        - **filters**: Semantic filters (location, equipment, point, property, state, etc.)
        - **refinement**: Specific item names for precise targeting
        - **intent**: Context for handling the trigger (who requested it, what action to take, priority)

        **Examples:**
        - One-shot immediate: mode='one_shot', end_time='2024-01-15T12:00:00', filters={{'point': 'Status_OpenState'}}
        - One-shot delayed: mode='one_shot', start_time='2024-01-15T10:00:00', end_time='2024-01-15T12:00:00'
        - Time window: mode='time_window', start_time='2024-01-15T09:00:00', end_time='2024-01-18T17:00:00'
        - With intent: intent={{'requested_by': 'John', 'action': 'Notify user when door opens', 'priority': 'high'}}
        """

def register(
    mcp, *, monitoring_config: MonitoringConfig, inventory
) -> MonitoringService:
    """Register monitoring tools and return monitoring service instance."""
    monitoring_store = create_monitoring_storage(monitoring_config)
    monitoring_service = MonitoringService(
        monitoring_store, monitoring_config, inventory
    )

    @mcp.tool(description=get_description())
    def create_monitoring_task(
        mode: str = Field(
            "one_shot", description="Monitoring mode: 'one_shot' or 'time_window'"
        ),
        filters: Optional[SearchFilters] = Field(
            None, description=FILTERS_DESCRIPTION_MONITORING
        ),
        refinement: Optional[ItemRefinement] = Field(
            None, description=REFINEMENT_DESCRIPTION
        ),
        intent: Optional[MonitoringIntent] = Field(
            None, description="Intent context for handling the monitoring trigger"
        ),
        start_time: Optional[str] = Field(
            None,
            description=f"Start time (ISO format). Default timezone: {monitoring_config.timezone}. Example: '2026-02-10T14:48:00' (interpreted as {monitoring_config.timezone} time)",
        ),
        end_time: Optional[str] = Field(
            None,
            description=f"End time (ISO format). Default timezone: {monitoring_config.timezone}. Example: '2026-02-10T14:58:00' (interpreted as {monitoring_config.timezone} time)",
        ),
    ) -> Dict[str, Any]:
        try:
            # Basic configuration check
            if not monitoring_config.webhook_url:
                return {
                    "success": False,
                    "error": "Monitoring webhook is not configured",
                    "message": (
                        "This tool requires extended configuration by an administrator. "
                        "Please set MONITORING_WEBHOOK_URL in the server environment."
                    ),
                }

            # Validate that we have items to monitor before creating the task
            if filters and inventory:
                monitored_items_info = _get_monitored_items_info(
                    filters, refinement, inventory
                )
                if monitored_items_info["count"] == 0:
                    return {
                        "success": False,
                        "error": "No items found",
                        "message": "No items match the specified filters. Please check your filter criteria.",
                        "suggestion": "Try using the get_available_semantic_entities tool to see what locations, equipment, and properties are available.",
                    }

            if end_time is None:
                return {
                    "success": False,
                    "error": "Invalid time range",
                    "message": "end_time is required.",
                }

            end = ensure_timezone_aware(datetime.fromisoformat(end_time))
            start = (
                ensure_timezone_aware(datetime.fromisoformat(start_time))
                if start_time
                else get_timezone_aware_datetime()
            )

            if start >= end:
                return {
                    "success": False,
                    "error": "Invalid time range",
                    "message": "Start time must be before end time.",
                }

            # Create task using service method (service delegates to backend)
            task = monitoring_service.create_monitoring_task(
                mode=MonitoringMode(mode),
                filters=filters.model_dump() if filters else None,
                refinement=refinement.item_names if refinement else None,
                intent=intent,
                start_time=start_time,  # Pass as string - service handles parsing
                end_time=end_time,  # Pass as string - service handles parsing
            )

            logger.info(
                "Created %s monitoring task %s",
                mode,
                task.task_id,
            )

            # Return formatted response (helper handles validation and formatting)
            return _format_task_response(
                task,
                include_monitored_items=True,
                filters=filters,
                refinement=refinement,
                inventory=inventory,
            )

        except Exception as e:
            logger.error("Error creating monitoring task: %s", e)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_monitoring_task_status(
        task_id: str = Field(..., min_length=1, max_length=50)
    ) -> Dict[str, Any]:
        """Get the current status and details of a monitoring task.

        Use this to check if a task is active, expired, triggered, or cancelled.
        Returns task configuration, creation time, timeout, and current status.
        Helps with debugging and monitoring long-running tasks.

        Example: task_id='monitor_abc12345' returns status='active' and full task metadata.
        """
        try:
            task = monitoring_service.monitoring_store.get_task(task_id)

            if not task:
                return {"success": False, "error": "Task not found", "task_id": task_id}

            # Return formatted response
            return _format_task_response(task)

        except Exception as e:
            logger.error("Error getting monitoring task status: %s", e)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def cancel_monitoring_task(
        task_id: str = Field(..., min_length=1, max_length=50)
    ) -> Dict[str, Any]:
        """Cancel an active monitoring task.

        Use this to stop monitoring before the timeout expires.
        Once cancelled, the task will not trigger webhooks on state changes.
        Returns confirmation of the cancellation.

        Example: task_id='monitor_abc12345' stops the monitoring task immediately.
        """
        try:
            task = monitoring_store.get_task(task_id)

            if not task:
                return {"success": False, "error": "Task not found", "task_id": task_id}

            task_update = TaskUpdate(status="cancelled", update_state_transition=True)
            monitoring_store.update_task(task_id, task_update)

            logger.info("Cancelled monitoring task %s", task_id)

            return {"success": True, "task_id": task_id, "status": "cancelled"}

        except Exception as e:
            logger.error("Error cancelling monitoring task: %s", e)
            return {"success": False, "error": str(e)}

    return monitoring_service


def _format_task_response(
    task: MonitoringTask,
    include_monitored_items: bool = False,
    filters=None,
    refinement=None,
    inventory=None,
) -> Dict[str, Any]:
    """Format task response consistently across all tools."""

    monitored_items_info = None

    # Get monitored items info for formatting (no validation here - done earlier)
    if include_monitored_items and filters and inventory:
        monitored_items_info = _get_monitored_items_info(filters, refinement, inventory)

    # Format success response
    response = {
        "success": True,
        "task_id": task.task_id,
        "status": task.status,
        "mode": task.mode,
        "time_window": {
            "start_time": task.time_window.start_time.isoformat(),
            "end_time": task.time_window.end_time.isoformat(),
        },
        "last_state_transition": task.last_state_transition.isoformat(),
    }

    # Add monitored items info (reuse the result from the single call)
    if monitored_items_info:
        response["monitored_items"] = {
            "count": monitored_items_info["count"],
            "items": (
                monitored_items_info["items"]
                if monitored_items_info["count"] <= 10
                else monitored_items_info["items"][:10] + ["..."]
            ),
        }

    return response


def _get_monitored_items_info(filters, refinement, inventory) -> Dict[str, Any]:
    """Get information about items that will be monitored."""
    if filters:
        items = inventory.get(
            location=filters.location,
            equipment=filters.equipment,
            point=filters.point,
            item_property=filters.property,
            readonly=filters.readonly,
            invert_selection=filters.invert_selection,
            refinement_item_names=refinement.item_names if refinement else None,
        )
    else:
        items = inventory.get(
            refinement_item_names=refinement.item_names if refinement else None
        )

    return {
        "count": len(items),
        "items": list(items),
    }
