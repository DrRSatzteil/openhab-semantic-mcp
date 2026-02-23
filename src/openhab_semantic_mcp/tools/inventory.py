"""
Inventory tools for OpenHAB semantic MCP server.
"""

from typing import Any, Dict, Optional
import logging

from pydantic import Field

from ..search.error_handler import create_error_response
from ..search.items import format_item_response, validate_filter_values
from ..search.models import ItemRefinement, SearchFilters
from ..search.descriptions import FILTERS_DESCRIPTION, REFINEMENT_DESCRIPTION
from ..exceptions import InvalidFilterError

logger = logging.getLogger(__name__)


def register(mcp, *, inventory) -> None:
    @mcp.tool()
    def get_items(
        filters: Optional[SearchFilters] = Field(None, description=FILTERS_DESCRIPTION),
        refinement: Optional[ItemRefinement] = Field(
            None, description=REFINEMENT_DESCRIPTION
        ),
    ) -> Dict[str, Any]:
        """Query OpenHAB semantic items with optional filters.

        Use this to discover and list items by location, equipment, point, or property.
        Supports hierarchical queries (e.g., location='Indoor_Room' matches all sub-rooms).
        For precise filtering, combine semantic filters with refinement (specific item names).
        Returns detailed item metadata including current state, type, and readonly status.

        Examples:
        - List all lights: filters={'equipment': 'LightSource', 'point': 'Control_Switch'}
        - Get temperature sensors: filters={'point': 'Measurement', 'property': 'Temperature'}
        - Specific items only: refinement={'item_names': ['light_livingroom', 'light_kitchen']}
        """
        try:
            if filters:
                validate_filter_values(inventory, filters)

            refinement_item_names = refinement.item_names if refinement else None

            if filters:
                items = inventory.get(
                    state=filters.state,
                    location=filters.location,
                    equipment=filters.equipment,
                    point=filters.point,
                    item_property=filters.property,
                    item_type=filters.type,
                    readonly=filters.readonly,
                    invert_selection=filters.invert_selection,
                    refinement_item_names=refinement_item_names,
                )
            else:
                items = inventory.get(refinement_item_names=refinement_item_names)

            item_details = [
                format_item_response(inventory.get_item(item_name))
                for item_name in items
            ]

            return {
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
        except InvalidFilterError as e:
            # Use error_handler for consistent response format
            return create_error_response(e, "get_items")
