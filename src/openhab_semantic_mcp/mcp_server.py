#!/usr/bin/env python3
"""
OpenHAB Semantic MCP Server - A lightweight MCP server for OpenHAB semantic operations.

This server provides tools for:
- Sending commands to OpenHAB items
- Getting item information from the semantic inventory
- Querying items by location, equipment, points, and properties
- Real-time state updates via SSE
"""

import abc
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Literal, Union
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, BaseModel

# Import the MCP server implementation
from mcp.server import FastMCP
from mcp.server.fastmcp import Context

# Import our modules
from .openhab_client import OpenHAB
from .inventory import Inventory, ExactStateFilter, RangeStateFilter


# Refinement Model to resolve ambiguity
class ItemRefinement(BaseModel):
    """
    Fallback parameter for ambiguity resolution.
    Only use when semantic filters are not unique.
    """

    item_names: List[str] = Field(
        description="Specific item names for additional filtering"
    )


class StateSelectionModel(BaseModel, abc.ABC):
    """
    Model for selecting states to filter by.
    """

    kind: Literal["exact", "range"] = Field(
        description="How to match states - 'exact' for exact matches, 'range' for numeric ranges"
    )


class ExactStateSelection(StateSelectionModel):
    """
    Model for selecting exact states to filter by.
    """

    kind: Literal["exact"] = "exact"
    states: List[str] = Field(description="List of exact state values to filter by")


class RangeStateSelection(StateSelectionModel):
    """
    Model for selecting numeric ranges to filter by.
    """

    kind: Literal["range"] = "range"
    lowerBound: Optional[float] = Field(
        None, description="Minimum value for the range (null for no lower limit)"
    )
    upperBound: Optional[float] = Field(
        None, description="Maximum value for the range (null for no upper limit)"
    )
    includeLower: bool = Field(True, description="Whether to include the lower bound")
    includeUpper: bool = Field(True, description="Whether to include the upper bound")

    class Config:
        """
        Config for RangeStateSelection model.
        """

        populate_by_name = True
        extra = "forbid"


# Standard Search Filters Model
class SearchFilters(BaseModel):
    """
    Standard semantic search filters for OpenHAB items.
    These are the primary filters for normal use cases.
    """

    location: Optional[str] = Field(
        None, description="Target location (e.g., 'LivingRoom', 'FirstFloor')"
    )
    equipment: Optional[str] = Field(
        None, description="Target equipment type (e.g., 'HVAC', 'Lighting')"
    )
    point: Optional[str] = Field(
        None, description="Target point type (e.g., 'Control', 'Measurement')"
    )
    property: Optional[str] = Field(
        None, description="Target property type (e.g., 'Temperature', 'Light')"
    )
    state: Optional[Union[ExactStateSelection, RangeStateSelection, None]] = Field(
        None, description="Target current state (e.g., 'ON', 'OFF', or a numeric range)"
    )
    readonly: Optional[bool] = Field(None, description="Filter by readonly status")
    invert_selection: Optional[Set[str]] = Field(
        None,
        description="Inverts the selection of the specified filters (e.g. 'point', 'state')",
    )


# Pydantic models for elicitation
class CommandConfirmation(BaseModel):
    """Confirmation model for large operations"""

    confirm: bool = Field(
        ..., description="Confirm whether to proceed with the operation"
    )


class StateUpdateConfirmation(BaseModel):
    """Confirmation model for large state updates"""

    confirm: bool = Field(
        ..., description="Confirm whether to proceed with the state update"
    )


def convert_state_selection(
    state_selection: Optional[Union[ExactStateSelection, RangeStateSelection]],
) -> Optional[Union[ExactStateFilter, RangeStateFilter]]:
    """
    Convert LLM StateSelectionModel to internal inventory filter.

    Args:
        state_selection: The LLM state selection model to convert

    Returns:
        Internal filter for inventory, or None if no selection
    """
    if not state_selection:
        return None

    if isinstance(state_selection, ExactStateSelection):
        return ExactStateFilter(states=state_selection.states)

    elif isinstance(state_selection, RangeStateSelection):
        return RangeStateFilter(
            lower=state_selection.lowerBound,
            upper=state_selection.upperBound,
            include_lower=state_selection.includeLower,
            include_upper=state_selection.includeUpper,
        )

    return None


# Get logger for this module
logger = logging.getLogger(__name__)


# Central error handler for MCP tools
def handle_error(func_name: str, e: Exception, context: str = "") -> Dict[str, Any]:
    """Centralized error handling for MCP tools."""
    error_msg = "Error %s: %s" % (func_name, str(e))
    if context:
        error_msg += " - %s" % context

    logger.error(error_msg)

    return {"success": False, "error": str(e), "message": error_msg}


# Load environment variables from .env file
env_file = Path(".env")
if env_file.exists():
    logger.info("Loading environment variables from %s", env_file)
    load_dotenv(env_file, verbose=True)

# Get OpenHAB settings from environment variables
OPENHAB_BASE_URL = os.environ.get("OPENHAB_BASE_URL", "http://localhost:8080")
OPENHAB_API_TOKEN = os.environ.get("OPENHAB_API_TOKEN")

# Get MCP server settings from environment variables
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
INVENTORY_REFRESH_MINUTES = int(os.environ.get("INVENTORY_REFRESH_MINUTES", "60"))

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Initialize MCP after environment is loaded
mcp = FastMCP(
    "OpenHAB Semantic MCP Server", host=MCP_HOST, port=MCP_PORT, log_level=LOG_LEVEL
)

# Initialize OpenHAB client and inventory
openhab = OpenHAB(OPENHAB_BASE_URL, api_token=OPENHAB_API_TOKEN)
inventory = Inventory()

# Load semantic points on startup
try:
    items = openhab.get_semantic_points()
    inventory.initialize_inventory(items)
    openhab.start_sse_listener(
        inventory.update_state_index, [item.name for item in items]
    )
    logger.info("Loaded %s semantic points into inventory", len(items))
except Exception as e:
    logger.error("Failed to load semantic points: %s", e)


def inventory_refresh_worker(openhab_client, inventory_manager):
    """Background worker to periodically refresh the inventory."""
    while True:
        try:
            # Sleep for the configured interval
            time.sleep(INVENTORY_REFRESH_MINUTES * 60)

            logger.info("Starting scheduled inventory refresh...")

            # Get fresh data first
            items = openhab_client.get_semantic_points()

            # Only update if we successfully got new data
            if items:
                # Create backup of current inventory state
                try:
                    # Update inventory with fresh data atomically
                    inventory_manager.initialize_inventory(items)

                    # Update SSE listener with new item names
                    item_names = [item.name for item in items]
                    openhab_client.update_sse_items(item_names)

                    logger.info(
                        "Inventory refresh completed: %s items loaded", len(items)
                    )

                except Exception as init_error:
                    logger.error("Failed to update inventory: %s", init_error)
                    logger.warning(
                        "Keeping existing inventory - refresh failed but system remains operational"
                    )
                    # Don't re-raise - keep existing inventory intact

            else:
                logger.warning(
                    "No items received from OpenHAB - keeping existing inventory"
                )

        except Exception as e:
            logger.error("Failed to refresh inventory: %s", e)
            logger.warning(
                "Keeping existing inventory - refresh failed but system remains operational"
            )


# Start inventory refresh thread
refresh_thread = threading.Thread(
    target=inventory_refresh_worker, args=(openhab, inventory), daemon=True
)
refresh_thread.start()
logger.info(
    "Inventory refresh thread started (interval: %s minutes)", INVENTORY_REFRESH_MINUTES
)


def validate_filter_values(filters: Optional[SearchFilters]) -> Optional[Dict[str, Any]]:
    """Validate that filter values exist in the inventory.
    
    Args:
        filters: SearchFilters to validate
        
    Returns:
        None if all values are valid, or error dict with guidance
    """
    if not filters:
        return None
        
    # Check each filter value - only convert to sets if we need to validate
    invalid_values = []
    
    if filters.location:
        available_locations = set(inventory.get_available_locations())
        if filters.location not in available_locations:
            invalid_values.append(f"location '{filters.location}'")
    
    if filters.equipment:
        available_equipment = set(inventory.get_available_equipment())
        if filters.equipment not in available_equipment:
            invalid_values.append(f"equipment '{filters.equipment}'")
    
    if filters.point:
        available_points = set(inventory.get_available_points())
        if filters.point not in available_points:
            invalid_values.append(f"point '{filters.point}'")
    
    if filters.property:
        available_properties = set(inventory.get_available_properties())
        if filters.property not in available_properties:
            invalid_values.append(f"property '{filters.property}'")
    
    if invalid_values:
        # Get available values for guidance (only if we have an error)
        available_locations = set(inventory.get_available_locations())
        available_equipment = set(inventory.get_available_equipment())
        available_points = set(inventory.get_available_points())
        available_properties = set(inventory.get_available_properties())
        available_item_types = set(inventory.get_available_types())
        
        return {
            "success": False,
            "error": "Invalid filter values specified",
            "invalid_values": invalid_values,
            "message": f"The following filter values don't exist in your OpenHAB system: {', '.join(invalid_values)}",
            "guidance": {
                "suggestion": "Use get_available_semantic_entities() first to discover valid values",
                "available_locations": sorted(list(available_locations))[:10],  # Show first 10
                "available_equipment": sorted(list(available_equipment))[:10],
                "available_points": sorted(list(available_points))[:10],
                "available_properties": sorted(list(available_properties))[:10],
                "available_item_types": sorted(list(available_item_types))[:10],
                "note": "Only showing first 10 values of each type. Use get_available_semantic_entities() for complete list."
            }
        }
    
    return None


def format_item_response(item) -> Dict[str, Any]:
    """Format an item for consistent API responses with LLM-friendly names.
    
    Args:
        item: Item object from inventory
        
    Returns:
        Formatted item dictionary with location hierarchy and equipment details
    """
    # Build location hierarchy
    location_hierarchy = []
    if item.location:
        current = item.location
        while current:
            location_hierarchy.append(current.name)
            current = current.parent
        location_hierarchy = list(reversed(location_hierarchy))
    
    # Build recursive equipment response
    def build_equipment_response(equipment) -> Dict[str, Any]:
        """Build recursive equipment response with parent chain."""
        response = {
            "type": equipment.type,
            "id": equipment.id,
            "label": equipment.label,
            "short_name": equipment.short_name,
        }
        if equipment.parent:
            response["parent"] = build_equipment_response(equipment.parent)
        return response
    
    return {
        "name": item.name,
        "state": item.state.value if item.state else None,
        "label": item.label,
        "type": item.type,
        "read_only": item.read_only,
        "allowed_commands": item.allowed_commands,
        "location": {
            "name": item.location.name,
            "short_name": item.location.short_name,
            "hierarchy": location_hierarchy
        } if item.location else None,
        "equipment": build_equipment_response(item.equipment) if item.equipment else None,
        "point": item.point,
        "property": item.property,
    }


# Discovery Tools
@mcp.tool()
def get_available_semantic_entities() -> Dict[str, Any]:
    """
    Get all available semantic entities (locations, equipment, points, properties) that can be used for filtering.

    This is the main discovery tool - use this to understand what's available in the OpenHAB system
    before using other tools. The returned entities can be used as filters in other tools.

    Returns:
        Hierarchical lists of all semantic entities with descriptions
    """
    try:
        return {
            "success": True,
            "entities": {
                "locations": {
                    "description": "Physical locations (rooms, floors, outdoor areas)",
                    "values": inventory.get_available_locations(),
                },
                "equipment": {
                    "description": "Equipment and devices (hierarchical - includes sub-types)",
                    "values": inventory.get_available_equipment(),
                },
                "points": {
                    "description": "Point types (hierarchical - includes sub-types)",
                    "values": inventory.get_available_points(),
                },
                "properties": {
                    "description": "Property types (hierarchical - includes sub-types)",
                    "values": inventory.get_available_properties(),
                },
                "item_types": {
                    "description": "OpenHAB item types (for understanding item capabilities). Note: Rollershutter uses 0=open, 100=closed semantics",
                    "values": inventory.get_available_types(),
                },
            },
        }
    except Exception as e:
        return handle_error("get_available_semantic_entities", e)


# Command Tools

async def _execute_item_operation(
    filters: Optional[SearchFilters],
    refinement: Optional[ItemRefinement],
    operation_type: str,
    value: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Execute operation on items based on semantic filters (DRY helper).
    
    Args:
        filters: Standard semantic search filters
        refinement: Item refinement for ambiguity resolution
        operation_type: "command" or "update"
        value: Command or new state value
        ctx: MCP context
        
    Returns:
        Operation results with success status and details
    """
    try:
        # Validate filter values
        validation_error = validate_filter_values(filters)
        if validation_error:
            return validation_error

        # Get refinement item names
        refinement_item_names = refinement.item_names if refinement else None

        # Get items based on filters
        if filters:
            # Convert state selection to internal filter
            state_filter = convert_state_selection(filters.state)

            items = inventory.get(
                location=filters.location,
                equipment=filters.equipment,
                point=filters.point,
                item_property=filters.property,
                state=state_filter,
                readonly=False,
                invert_selection=filters.invert_selection,
                refinement_item_names=refinement_item_names,
            )
        else:
            # No filters provided
            items = inventory.get(refinement_item_names=refinement_item_names)

        if not items:
            return {
                "success": False,
                "message": "No items found matching the specified criteria",
                "filters": {
                    "location": filters.location if filters else None,
                    "equipment": filters.equipment if filters else None,
                    "point": filters.point if filters else None,
                    "property": filters.property if filters else None,
                    "state": str(filters.state) if filters and filters.state else None,
                },
                "items_targeted": 0,
                "results": [],
            }

        results = []
        successful_operations = 0

        # Execute operation on each item
        for item_name in items:
            item = inventory.get_item(item_name)
            result = None
            
            if not item:
                continue

            if item.read_only:
                error_result = {
                    "item_name": item_name,
                    "success": False,
                    "command" if operation_type == "command" else "new_state": value,
                    "error": "Item is read only - cannot send commands or updates"
                }
                
                # Add item type info for better debugging
                if item:
                    error_result["item_type"] = item.type
                
                results.append(error_result)
                continue

            try:
                if operation_type == "command":
                    # Send command
                    result = openhab.send_command(item_name, value)
                elif operation_type == "update":
                    # Update state
                    result = openhab.post_update(item_name, value)
                else:
                    raise ValueError(f"Unknown operation type: {operation_type}")

                # Check result
                if result and result.get("success"):
                    successful_operations += 1
                    results.append({
                        "item_name": item_name,
                        "success": True,
                        "command" if operation_type == "command" else "new_state": value,
                    })
                else:
                    # Operation failed
                    error_result = {
                        "item_name": item_name,
                        "success": False,
                        "command" if operation_type == "command" else "new_state": value,
                        "error": result.get("error", "Unknown error") if result else "No response from OpenHAB"
                    }
                    
                    # Add item type info if available
                    if item:
                        error_result["item_type"] = item.type
                    
                    results.append(error_result)
                    
            except Exception as e:
                results.append({
                    "item_name": item_name,
                    "success": False,
                    "command" if operation_type == "command" else "new_state": value,
                    "error": str(e),
                })

        # Determine overall success
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
    except Exception as e:
        return handle_error(f"{operation_type}_entities", e)


# Command Tools
@mcp.tool()
async def send_command_to_entities(
    filters: Optional[SearchFilters] = Field(
        None, description="Standard semantic search filters"
    ),
    refinement: Optional[ItemRefinement] = Field(
        None,
        description=(
            "ONLY use for ambiguity! "
            "List of item names for additional filtering. "
            "Combined with semantic filters. "
            "Normal semantic filters take priority. "
            "IMPORTANT: Only use item names that were returned by previous get_items() calls. "
            "DO NOT invent or guess item names - this will cause errors."
        ),
    ),
    command: str = Field(
        ..., description="Command to send (e.g., 'ON', 'OFF', 'TOGGLE', '20.5 °C')"
    ),
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Send a command to OpenHAB items based on semantic filters.

    This tool finds items matching your semantic criteria and sends the command to them.
    Use get_available_semantic_entities() first to see what filters are available.

    Examples:
    - Turn off all lights: filters=SearchFilters(equipment="LightSource", point="Control"), command="OFF"
    - Set heating to 20°C: filters=SearchFilters(equipment="HVAC", point="Setpoint"), command="20 °C"
    - Close all windows: filters=SearchFilters(point="Control", property="Opening"), command="CLOSE"
    - Turn off lights in LivingRoom: filters=SearchFilters(location="LivingRoom", point="Control"), command="OFF"

    REFINEMENT USAGE:
    - Only use when semantic filters are ambiguous
    - IMPORTANT: Only use item names that were returned by previous get_items() calls
    - DO NOT invent or guess item names - this will cause errors

    Args:
        filters: Standard semantic search filters
        refinement: List of specific item names for additional filtering
        command: Command to send to matching items

    Returns:
        Success status and details of which items were targeted
    """
    return await _execute_item_operation(filters, refinement, "command", command, ctx)


def _validate_and_format_command_error(item_name: str, command: str, item_type: str, error_msg: str) -> dict:
    """Generate a meaningful error message for failed commands based on item type.
    
    Args:
        item_name: Name of the item
        command: Command that was sent
        item_type: OpenHAB item type
        error_msg: Original error message from OpenHAB
        
    Returns:
        Formatted error result with allowed commands
    """
    # Add type-specific guidance based on OpenHAB item types
    guidance = ""
    if item_type == "Call":
        guidance = " Use: REFRESH"
    elif item_type == "Color":
        guidance = " Use ON/OFF, INCREASE/DECREASE, 0-100 (brightness), hue (0-359),saturation (0-100),brightness (0-100) (e.g., 120,100,50), REFRESH"
    elif item_type == "Contact":
        guidance = " Use: OPEN, CLOSED, REFRESH"
    elif item_type == "DateTime":
        guidance = " Use datetime format (e.g., 2023-12-25T14:30:00)"
    elif item_type == "Number":
        guidance = " Use numeric values, strings with units (e.g., '22 °C'), REFRESH"
    elif item_type == "String":
        guidance = " Use text values, REFRESH"
    elif item_type == "Location":
        guidance = " Use latitude,longitude format (e.g., 52.5200,13.4050), REFRESH"
    elif item_type == "Dimmer":
        guidance = " Use ON/OFF, INCREASE/DECREASE, 0-100, REFRESH"
    elif item_type == "Player":
        guidance = " Use: PLAY, PAUSE, NEXT, PREVIOUS, REWIND, FASTFORWARD, REFRESH"
    elif item_type == "Rollershutter":
        guidance = " Use UP/DOWN/STOP, 0-100 for position (0=Open, 100=Closed), REFRESH"
    elif item_type == "Switch":
        guidance = " Use: ON, OFF, REFRESH"
    elif item_type == "Group":
        guidance = " Usage depends on group members"
    else:
        guidance = " Unknown item type - check OpenHAB documentation"
    
    return {
        "item_name": item_name,
        "success": False,
        "command": command,
        "error": f"{error_msg}{guidance}",
        "item_type": item_type,
    }


@mcp.tool()
async def update_entities_state(
    filters: Optional[SearchFilters] = Field(
        None, description="Standard semantic search filters"
    ),
    refinement: Optional[ItemRefinement] = Field(
        None,
        description=(
            "ONLY use for ambiguity! "
            "List of item names for additional filtering. "
            "Combined with semantic filters. "
            "Normal semantic filters take priority. "
            "IMPORTANT: Only use item names that were returned by previous get_items() calls. "
            "DO NOT invent or guess item names - this will cause errors."
        ),
    ),
    new_state: str = Field(
        ..., description="New state value (e.g., 'ON', 'OFF', '20.5', 'Hello World')"
    ),
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Update the state of OpenHAB items based on semantic filters.

    This tool finds items matching your semantic criteria and updates their state.
    Use get_available_semantic_entities() first to see what filters are available.

    Examples:
    - Set all lights to ON: filters=SearchFilters(equipment="LightSource", point="Control"), new_state="ON"
    - Set temperature to 20°C: filters=SearchFilters(equipment="HVAC", point="Setpoint"), new_state="20 °C"
    - Update all sensors: filters=SearchFilters(point="Measurement"), new_state="42"

    REFINEMENT USAGE:
    - Only use when semantic filters are ambiguous
    - IMPORTANT: Only use item names that were returned by previous get_items() calls
    - DO NOT invent or guess item names - this will cause errors

    Args:
        filters: Standard semantic search filters
        refinement: List of specific item names for additional filtering
        new_state: New state value for matching items

    Returns:
        Success status and details of which items were updated
    """
    return await _execute_item_operation(filters, refinement, "update", new_state, ctx)


# Inventory Query Tools
@mcp.tool()
def get_items(
    filters: Optional[SearchFilters] = Field(
        None, description="Standard semantic search filters"
    ),
    refinement: Optional[ItemRefinement] = Field(
        None,
        description=(
            "ONLY use for ambiguity! "
            "List of item names for additional filtering. "
            "Combined with semantic filters. "
            "Normal semantic filters take priority. "
            "IMPORTANT: Only use item names that were returned by previous get_items() calls. "
            "DO NOT invent or guess item names - this will cause errors."
        ),
    ),
) -> Dict[str, Any]:
    """
    Get items from the semantic inventory with optional filtering.

    This is the main query method - you can combine any filters:
    - Get all items: no parameters
    - Get items by location: filters=SearchFilters(location="LivingRoom")
    - Get all lights: filters=SearchFilters(equipment="LightSource")
    - Get temperature sensors: filters=SearchFilters(point="Measurement", property="Temperature")
    - Get HVAC items: filters=SearchFilters(equipment="HVAC")
    - Get ON items in LivingRoom: filters=SearchFilters(location="LivingRoom", state="ON")

    REFINEMENT USAGE:
    - Only use when semantic filters are ambiguous
    - refinement.item_names will be combined with semantic filters
    - Normal semantic filters always take priority
    - IMPORTANT: Only use item names that were returned by previous get_items() calls
    - DO NOT invent or guess item names - this will cause errors

    Args:
        filters: Standard semantic search filters
        refinement: List of specific item names for additional filtering

    Returns:
        List of matching item names and metadata
    """
    try:
        # Validate filter values first
        if filters:
            validation_error = validate_filter_values(filters)
            if validation_error:
                return validation_error
        
        refinement_item_names = refinement.item_names if refinement else None

        # Extract filter values from SearchFilters model
        if filters:
            # Convert state selection to internal filter
            state_filter = convert_state_selection(filters.state)

            items = inventory.get(
                state=state_filter,
                location=filters.location,
                equipment=filters.equipment,
                point=filters.point,
                item_property=filters.property,
                readonly=filters.readonly,
                invert_selection=filters.invert_selection,
                refinement_item_names=refinement_item_names,
            )
        else:
            # No filters provided
            items = inventory.get(refinement_item_names=refinement_item_names)

        # Get detailed information for each item
        item_details = []
        for item_name in items:
            item = inventory.get_item(item_name)
            if item:
                item_details.append(format_item_response(item))

        result = {
            "success": True,
            "count": len(items),
            "refinement_applied": refinement is not None,
            "filters": {
                "location": filters.location if filters else None,
                "equipment": filters.equipment if filters else None,
                "point": filters.point if filters else None,
                "property": filters.property if filters else None,
                "state": filters.state if filters else None,
                "readonly": filters.readonly if filters else None,
                "invert_selection": filters.invert_selection if filters else None,
            },
            "items": item_details,
        }

        return result
    except Exception as e:
        return handle_error("get_items", e)


def run_server():
    """Run the MCP server."""
    try:
        logger.info("Starting OpenHAB Semantic MCP Server on %s:%s", MCP_HOST, MCP_PORT)
        logger.info("Connected to OpenHAB at %s", OPENHAB_BASE_URL)
        logger.info("Using MCP transport: %s", MCP_TRANSPORT)
        mcp.run(transport=MCP_TRANSPORT)
    except Exception as e:
        logger.error("Server error: %s", e)
        raise
    finally:
        # Ensure SSE listener is stopped when server exits
        try:
            openhab.stop_sse_listener()
            logger.info("SSE listener stopped on server shutdown")
        except Exception as e:
            logger.error("Error stopping SSE listener during shutdown: %s", e)


if __name__ == "__main__":
    run_server()
