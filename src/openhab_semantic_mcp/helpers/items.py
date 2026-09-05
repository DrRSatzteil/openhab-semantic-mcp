from typing import Any, Dict, Optional, Union

from ..exceptions import InvalidFilterError
from ..inventory import ExactStateFilter, Inventory, RangeStateFilter
from .models import ExactStateSelection, RangeStateSelection, SearchFilters


def convert_state_selection(
    state_selection: Optional[Union[ExactStateSelection, RangeStateSelection]],
) -> Optional[Union[ExactStateFilter, RangeStateFilter]]:
    """
    Convert a state selection to a filter.
    """
    if not state_selection:
        return None

    if isinstance(state_selection, ExactStateSelection):
        return ExactStateFilter(states=state_selection.states)

    if isinstance(state_selection, RangeStateSelection):
        return RangeStateFilter(
            lower=state_selection.lowerBound,
            upper=state_selection.upperBound,
            include_lower=state_selection.includeLower,
            include_upper=state_selection.includeUpper,
        )


def validate_filter_values(
    inventory: Inventory, filters: Optional[SearchFilters]
) -> Optional[Dict[str, Any]]:
    """
    Validate filter values.
    """
    if not filters:
        return None

    invalid_values = []
    guidance_data = {}

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
        # Build guidance data
        available_locations = set(inventory.get_available_locations())
        available_equipment = set(inventory.get_available_equipment())
        available_points = set(inventory.get_available_points())
        available_properties = set(inventory.get_available_properties())
        available_item_types = set(inventory.get_available_types())

        guidance_data = {
            "suggestion": "Use get_available_semantic_entities() first to discover valid values",
            "available_locations": sorted(list(available_locations))[:10],
            "available_equipment": sorted(list(available_equipment))[:10],
            "available_points": sorted(list(available_points))[:10],
            "available_properties": sorted(list(available_properties))[:10],
            "available_item_types": sorted(list(available_item_types))[:10],
            "note": (
                "Only showing first 10 values of each type. "
                "Use get_available_semantic_entities() for complete list."
            ),
        }

        # Raise InvalidFilterError with all guidance information
        raise InvalidFilterError(
            filter_name="multiple_filters",
            filter_value=invalid_values,
            reason=f"The following filter values don't exist in your openHAB system: {', '.join(invalid_values)}",
            guidance=guidance_data,
        )

    return None


def format_item_response(item) -> Dict[str, Any]:
    """
    Formats an item for a tool response
    """
    location_hierarchy = []
    if item.location:
        current = item.location
        while current:
            location_hierarchy.append(current.name)
            current = current.parent
        location_hierarchy = list(reversed(location_hierarchy))

    def build_equipment_response(equipment) -> Dict[str, Any]:
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
        "allowed_states": item.allowed_states,
        "command_labels": item.command_labels,
        "state_labels": item.state_labels,
        "location": (
            {
                "name": item.location.name,
                "short_name": item.location.short_name,
                "hierarchy": location_hierarchy,
            }
            if item.location
            else None
        ),
        "equipment": (
            build_equipment_response(item.equipment) if item.equipment else None
        ),
        "point": item.point,
        "property": item.property,
    }
