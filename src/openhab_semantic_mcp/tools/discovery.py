"""
Discovery tools for OpenHAB semantic MCP server.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def register(mcp, *, inventory) -> None:
    @mcp.tool()
    def get_available_semantic_entities() -> Dict[str, Any]:
        """Discover available semantic entities in the OpenHAB installation.

        Returns all available locations, equipment types, points, properties, and item types.
        Use this to understand the semantic model and valid filter values.
        Hierarchical values include sub-types (e.g., 'Indoor_Room' matches 'Indoor_Room_LivingRoom').

        Example response includes:
        - locations: ['Indoor', 'Outdoor', 'Indoor_Room_LivingRoom']
        - equipment: ['LightSource', 'HVAC', 'Sensor']
        - points: ['Control_Switch', 'Measurement', 'Status']
        - properties: ['Temperature', 'Light', 'Humidity']
        - item_types: ['Switch', 'Dimmer', 'Number', 'Rollershutter']
        """
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
                    "description": "openHAB item types (for understanding item capabilities). Note: Rollershutter uses 0=open, 100=closed semantics",
                    "values": inventory.get_available_types(),
                },
            },
        }
