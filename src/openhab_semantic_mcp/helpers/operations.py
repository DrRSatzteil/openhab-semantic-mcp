"""
Helper functions for item operations.
"""

import logging
from typing import Any, Dict, Optional

from ..openhab_client import OpenHAB
from ..inventory import Inventory
from ..exceptions import (
    ItemCommandError,
    ItemStateError,
    InvalidFilterError,
    ValidationError,
)
from .error_handler import create_error_response
from .items import validate_filter_values
from .models import ItemRefinement, SearchFilters

logger = logging.getLogger(__name__)


async def execute_item_operation(
    *,
    openhab: OpenHAB,
    inventory: Inventory,
    filters: Optional[SearchFilters],
    refinement: Optional[ItemRefinement],
    operation_type: str,
    value: str,
) -> Dict[str, Any]:
    """
    Execute an item operation (command or state update) on filtered items.

    Args:
        openhab: OpenHAB client instance
        inventory: Inventory instance
        filters: Search filters to apply
        refinement: Item refinement to apply
        operation_type: Type of operation ('command' or 'update')
        value: Value to set/update

    Returns:
        Dictionary with operation results
    """
    try:
        if filters:
            validate_filter_values(inventory, filters)

        refinement_item_names = refinement.item_names if refinement else None

        if filters:
            items = inventory.get(
                location=filters.location,
                equipment=filters.equipment,
                point=filters.point,
                item_property=filters.property,
                state=filters.state,
                readonly=False,
                invert_selection=filters.invert_selection,
                refinement_item_names=refinement_item_names,
            )
        else:
            items = inventory.get(refinement_item_names=refinement_item_names)

        if not items:
            # Use InvalidFilterError for consistent error handling when no items match filters
            raise InvalidFilterError(
                filter_name="search_criteria",
                filter_value={
                    "location": filters.location if filters else None,
                    "equipment": filters.equipment if filters else None,
                    "point": filters.point if filters else None,
                    "property": filters.property if filters else None,
                    "state": str(filters.state) if filters and filters.state else None,
                },
                reason="No items found matching the specified criteria",
                guidance={
                    "suggestion": "Try broadening your search criteria or use get_available_semantic_entities() to discover valid values",
                    "next_steps": [
                        "Check if filter values exist using get_available_semantic_entities()",
                        "Try removing some filters to broaden the search",
                        "Verify item names if using refinement",
                    ],
                },
            )

        results = []
        successful_operations = 0
        overall_success = False

        for item_name in items:
            item = inventory.get_item(item_name)
            if not item:
                continue

            if item.read_only:
                error_result = create_error_response(
                    ItemStateError(
                        item_name,
                        value,
                        "Item is read only - cannot send commands or updates",
                    ),
                    "read_only_check",
                )
                results.append(error_result)
                continue

            if operation_type == "command" and item.allowed_commands:
                if value not in item.allowed_commands:
                    error_result = create_error_response(
                        ItemCommandError(
                            item_name,
                            value,
                            f"Command '{value}' not allowed. Allowed commands: {item.allowed_commands}",
                        ),
                        "command_validation",
                    )
                    results.append(error_result)
                    continue

            if operation_type == "update" and item.allowed_states:
                if value not in item.allowed_states:
                    error_result = create_error_response(
                        ItemStateError(
                            item_name,
                            value,
                            f"State '{value}' not allowed. Allowed states: {item.allowed_states}",
                        ),
                        "state_validation",
                    )
                    results.append(error_result)
                    continue

            try:
                if operation_type == "command":
                    result = openhab.send_command(item_name, value)
                elif operation_type == "update":
                    result = openhab.post_update(item_name, value)
                else:
                    raise ValidationError(
                        "operation_type",
                        operation_type,
                        f"Unknown operation type: {operation_type}",
                    )

                if result and result.get("success"):
                    successful_operations += 1
                    results.append(
                        {
                            "item_name": item_name,
                            "success": True,
                            (
                                "command"
                                if operation_type == "command"
                                else "new_state"
                            ): value,
                        }
                    )
                else:
                    results.append(
                        {
                            "item_name": item_name,
                            "success": False,
                            (
                                "command"
                                if operation_type == "command"
                                else "new_state"
                            ): value,
                            "error": (
                                result.get("error", "Unknown error")
                                if result
                                else "No response from openHAB"
                            ),
                            "item_type": item.type,
                        }
                    )

            except Exception as e:
                # Convert custom exceptions to error response format
                error_response = create_error_response(e, f"{operation_type}_operation")
                results.append(
                    {
                        "item_name": item_name,
                        "success": False,
                        (
                            "command" if operation_type == "command" else "new_state"
                        ): value,
                        "error": error_response.get("message", str(e)),
                        "error_type": error_response.get("error_type", "Exception"),
                        "item_type": item.type,
                    }
                )
                continue
        overall_success = successful_operations > 0

        return {
            "success": overall_success,
            "command" if operation_type == "command" else "new_state": value,
            "items_targeted": len(items),
            "successful_operations": successful_operations,
            "filters": {
                "location": filters.location if filters else None,
                "equipment": filters.equipment if filters else None,
                "point": filters.point if filters else None,
                "property": filters.property if filters else None,
                "state": str(filters.state) if filters and filters.state else None,
            },
            "results": results,
        }

    except InvalidFilterError as e:
        # Use error_handler for consistent response format
        return create_error_response(e, f"{operation_type}_entities")

    except (ItemCommandError, ItemStateError, ValidationError) as e:
        # Handle expected item operation errors
        return create_error_response(e, f"{operation_type}_entities")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        # Handle system-level errors that might affect operations
        return create_error_response(e, f"{operation_type}_entities")
