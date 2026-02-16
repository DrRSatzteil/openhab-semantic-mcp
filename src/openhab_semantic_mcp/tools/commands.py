"""
Command tools for OpenHAB semantic MCP server.
"""

import logging
from typing import Any, Dict, Optional

from pydantic import Field

from ..helpers.models import ItemRefinement, SearchFilters
from ..helpers.descriptions import FILTERS_DESCRIPTION, REFINEMENT_DESCRIPTION
from ..helpers.operations import execute_item_operation

logger = logging.getLogger(__name__)


def register(mcp, *, openhab, inventory) -> None:
    @mcp.tool()
    async def send_command_to_entities(
        filters: Optional[SearchFilters] = Field(None, description=FILTERS_DESCRIPTION),
        refinement: Optional[ItemRefinement] = Field(
            None, description=REFINEMENT_DESCRIPTION
        ),
        command: str = Field(
            ..., description="Command to send (e.g., 'ON', 'OFF', 'TOGGLE', '20.5 °C')"
        ),
    ) -> Dict[str, Any]:
        """Send a command to matching OpenHAB items.

        Use this to control devices (lights, switches, thermostats, etc.) by semantic criteria.
        The command is only sent to writable items that accept the command.
        Combines semantic filtering with optional refinement for precise targeting.

        Examples:
        - Turn off all lights: filters={'equipment': 'LightSource', 'point': 'Control_Switch'}, command='OFF'
        - Set temperature: filters={'point': 'Control', 'property': 'Temperature'}, command='21 °C'
        - Specific device: refinement={'item_names': ['light_livingroom']}, command='TOGGLE'
        """
        return await execute_item_operation(
            openhab=openhab,
            inventory=inventory,
            filters=filters,
            refinement=refinement,
            operation_type="command",
            value=command,
        )

    @mcp.tool()
    async def update_entities_state(
        filters: Optional[SearchFilters] = Field(None, description=FILTERS_DESCRIPTION),
        refinement: Optional[ItemRefinement] = Field(
            None, description=REFINEMENT_DESCRIPTION
        ),
        new_state: str = Field(
            ...,
            description="New state value (e.g., 'ON', 'OFF', '20.5', 'Hello World')",
        ),
    ) -> Dict[str, Any]:
        """Update the state of matching OpenHAB items.

        Use this to set item states (e.g., sensor values, text states) by semantic criteria.
        The update is only applied to writable items that accept the state.
        Combines semantic filtering with optional refinement for precise targeting.

        Examples:
        - Set all switches to ON: filters={'point': 'Control_Switch'}, new_state='ON'
        - Update temperature reading: filters={'property': 'Temperature'}, new_state='22.5'
        - Specific item: refinement={'item_names': ['sensor_humidity']}, new_state='45 %'
        """
        return await execute_item_operation(
            openhab=openhab,
            inventory=inventory,
            filters=filters,
            refinement=refinement,
            operation_type="update",
            value=new_state,
        )
