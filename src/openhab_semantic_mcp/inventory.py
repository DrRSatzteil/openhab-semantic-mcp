"""Inventory management for OpenHAB semantic items.

This module provides indexing and filtering capabilities for OpenHAB items,
including semantic filtering by location, equipment, point, and property.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import List, Optional, Set, Union

from .dto import Item, State


@dataclass
class ExactStateFilter:
    """Internal filter for exact state matches with multiple values."""

    states: List[str]


@dataclass
class RangeStateFilter:
    """Internal filter for numeric state ranges with inclusive/exclusive bounds."""

    lower: Optional[float] = None
    upper: Optional[float] = None
    include_lower: bool = True
    include_upper: bool = True


class Inventory:
    """Thread-safe inventory for OpenHAB items with semantic indexing and filtering."""

    def __init__(self):
        """Initialize empty inventory with semantic indexes."""
        self._items = {}  # name -> Item
        self._location_index = defaultdict(set)
        self._equipment_index = defaultdict(set)
        self._point_index = defaultdict(set)
        self._property_index = defaultdict(set)
        self._state_index = defaultdict(set)
        self._readonly_index = defaultdict(set)
        self._lock = RLock()

    def _build_indexes(self, items: list[Item]) -> tuple:
        """Build all semantic indexes from items.

        Args:
            items: List of OpenHAB items to index

        Returns:
            Tuple of (items_dict, location_index, equipment_index, point_index,
                    property_index, state_index, readonly_index)
        """
        new_items = {}
        new_location_index = defaultdict(set)
        new_equipment_index = defaultdict(set)
        new_point_index = defaultdict(set)
        new_property_index = defaultdict(set)
        new_state_index = defaultdict(set)
        new_readonly_index = defaultdict(set)

        for item in items:
            new_items[item.name] = item

            # Handle state indexing
            if item.state:
                new_state_index[item.state.value].add(item.name)

            # Handle location indexing (including hierarchy)
            if item.location:
                new_location_index[item.location.name].add(item.name)
                # Add to all parent locations for hierarchical queries
                current_location = item.location
                while current_location.parent:
                    new_location_index[current_location.parent.name].add(item.name)
                    current_location = current_location.parent

            # Handle equipment indexing (including hierarchy)
            if item.equipment and item.equipment.type:
                new_equipment_index[item.equipment.type].add(item.name)
                # Add to all parent equipment for hierarchical queries
                equipment_hierarchy = item.equipment.type.split("_")
                for i in range(len(equipment_hierarchy) - 1):
                    parent_equipment = "_".join(equipment_hierarchy[: i + 1])
                    new_equipment_index[parent_equipment].add(item.name)

            # Handle point indexing (including hierarchy)
            if item.point and item.point.strip():
                new_point_index[item.point].add(item.name)
                # Add to all parent points for hierarchical queries
                point_hierarchy = item.point.split("_")
                for i in range(len(point_hierarchy) - 1):
                    parent_point = "_".join(point_hierarchy[: i + 1])
                    new_point_index[parent_point].add(item.name)

            # Handle property indexing (including hierarchy)
            if item.property and item.property.strip():
                new_property_index[item.property].add(item.name)
                # Add to all parent properties for hierarchical queries
                property_hierarchy = item.property.split("_")
                for i in range(len(property_hierarchy) - 1):
                    parent_property = "_".join(property_hierarchy[: i + 1])
                    new_property_index[parent_property].add(item.name)

            # Handle readonly indexing
            if item.read_only:
                new_readonly_index[item.read_only].add(item.name)

        return (
            new_items,
            new_location_index,
            new_equipment_index,
            new_point_index,
            new_property_index,
            new_state_index,
            new_readonly_index,
        )

    def initialize_inventory(self, items: list[Item]):
        """Initialize inventory with items and build semantic indexes.

        Args:
            items: List of OpenHAB items to index
        """
        with self._lock:
            (
                self._items,
                self._location_index,
                self._equipment_index,
                self._point_index,
                self._property_index,
                self._state_index,
                self._readonly_index,
            ) = self._build_indexes(items)

    def get_available_locations(self) -> list[str]:
        """Get all available location names from the inventory.

        Returns:
            Sorted list of location names
        """
        with self._lock:
            return sorted(list(self._location_index.keys()))

    def get_available_equipment(self) -> list[str]:
        """Get all available equipment types from the inventory.

        Returns:
            Sorted list of equipment types
        """
        with self._lock:
            return sorted(list(self._equipment_index.keys()))

    def get_available_points(self) -> list[str]:
        """Get all available point types from the inventory.

        Returns:
            Sorted list of point types
        """
        with self._lock:
            return sorted(list(self._point_index.keys()))

    def get_available_properties(self) -> list[str]:
        """Get all available property types from the inventory.

        Returns:
            Sorted list of property types
        """
        with self._lock:
            return sorted(list(self._property_index.keys()))

    def update_state_index(self, item_name: str, new_state: State):
        """Update the state index for a specific item.

        Args:
            item_name: Name of the item to update
            new_state: New state value for the item
        """
        with self._lock:
            if item_name not in self._items:
                return

            item = self._items[item_name]
            old_state = item.state.value

            if old_state == new_state.value:
                return

            # Remove from old state index
            if old_state is not None:
                self._state_index[old_state].discard(item_name)
                # Clean up empty state keys
                if not self._state_index[old_state]:
                    del self._state_index[old_state]

            # Update item state
            item.state = new_state

            # Add to new state index
            self._state_index[new_state.value].add(item_name)

    def get_item(self, item_name: str):
        """Get a specific item from the inventory.

        Args:
            item_name: Name of the item to retrieve

        Returns:
            Item object if found, None otherwise
        """
        return self._items.get(item_name)

    def get(
        self,
        state: Optional[Union[ExactStateFilter, RangeStateFilter]] = None,
        location: str = None,
        equipment: str = None,
        point: str = None,
        item_property: str = None,
        readonly: bool = None,
        invert_selection: Set[str] = None,
        refinement_item_names: List[str] = None,
    ) -> set[str]:
        """
        Generic method to get items filtered by any combination of criteria.

        Args:
            state: Filter by state filter (ExactStateFilter/RangeStateFilter)
            location: Filter by location (includes sub-locations)
            equipment: Filter by equipment type (includes sub-types)
            point: Filter by point type (includes sub-types)
            item_property: Filter by property type (includes sub-types)
            readonly: Filter readonly items
            invert_selection: Invert the selection of the specified filters
            refinement_item_names: List of specific item names for additional filtering
        Returns:
            Set of item names matching all specified criteria
        """
        with self._lock:
            # Collect all specified filters
            filters = []

            # Ensure invert_selection is a set for efficient lookup
            invert_set = set(invert_selection) if invert_selection else set()

            if state:
                state_items = set()

                if isinstance(state, ExactStateFilter):
                    # Exact state filter - union of all specified states
                    for state_value in state.states:
                        state_items.update(self._state_index.get(state_value, set()))
                elif isinstance(state, RangeStateFilter):
                    # Range state filter - need to parse numeric values
                    for item_name, item in self._items.items():
                        if item.state and self._is_state_in_range(
                            item.state.value, state
                        ):
                            state_items.add(item_name)

                if "state" in invert_set:
                    filters.append(set(self._items.keys()) - state_items)
                else:
                    filters.append(state_items)
            if location:
                if "location" in invert_set:
                    filters.append(
                        set(self._items.keys())
                        - self._location_index.get(location, set())
                    )
                else:
                    filters.append(self._location_index.get(location, set()))
            if equipment:
                if "equipment" in invert_set:
                    filters.append(
                        set(self._items.keys())
                        - self._equipment_index.get(equipment, set())
                    )
                else:
                    filters.append(self._equipment_index.get(equipment, set()))
            if point:
                if "point" in invert_set:
                    filters.append(
                        set(self._items.keys()) - self._point_index.get(point, set())
                    )
                else:
                    filters.append(self._point_index.get(point, set()))
            if item_property:
                if "property" in invert_set:
                    filters.append(
                        set(self._items.keys())
                        - self._property_index.get(item_property, set())
                    )
                else:
                    filters.append(self._property_index.get(item_property, set()))
            if readonly:
                if "readonly" in invert_set:
                    filters.append(
                        set(self._items.keys())
                        - self._readonly_index.get(readonly, set())
                    )
                else:
                    filters.append(self._readonly_index.get(readonly, set()))

            # If no filters, return all items
            if not filters:
                return set(self._items.keys())

            # Start with the first filter (make a copy)
            result = filters[0].copy()

            # Apply remaining filters
            for filter_set in filters[1:]:
                result = result.intersection(filter_set)

            # Apply refinement if provided
            if refinement_item_names:
                refinement_set = set(refinement_item_names)
                result = result.intersection(refinement_set)

            return result

    def get_locations(self) -> set[str]:
        """Get all available locations from the inventory.

        Returns:
            Set of location names
        """
        with self._lock:
            return set(self._location_index.keys())

    def get_equipments(self) -> set[str]:
        """Get all available equipment types from the inventory.

        Returns:
            Set of equipment type names
        """
        with self._lock:
            return set(self._equipment_index.keys())

    def get_points(self) -> set[str]:
        """Get all available point types from the inventory.

        Returns:
            Set of point type names
        """
        with self._lock:
            return set(self._point_index.keys())

    def get_properties(self) -> set[str]:
        """Get all available property types from the inventory.

        Returns:
            Set of property type names
        """
        with self._lock:
            return set(self._property_index.keys())

    def _is_state_in_range(
        self, state_value: str, range_filter: RangeStateFilter
    ) -> bool:
        """
        Check if a state value falls within a numeric range.

        Args:
            state_value: The state value to check (e.g., "23.5 °C", "100 %", "50", etc.)
            range_filter: The range filter to check against

        Returns:
            True if the state value is within the range, False otherwise
        """
        try:
            # Extract numeric value from state string
            # Handle formats like "23.5 °C", "100 %", "50", etc.
            numeric_match = re.search(r"[-+]?\d*\.?\d+", state_value)
            if not numeric_match:
                return False

            numeric_value = float(numeric_match.group())

            # Check lower bound if specified
            if range_filter.lower is not None:
                lower_check = (
                    numeric_value >= range_filter.lower
                    if range_filter.include_lower
                    else numeric_value > range_filter.lower
                )
                if not lower_check:
                    return False

            # Check upper bound if specified
            if range_filter.upper is not None:
                upper_check = (
                    numeric_value <= range_filter.upper
                    if range_filter.include_upper
                    else numeric_value < range_filter.upper
                )
                if not upper_check:
                    return False

            # If no bounds specified, all values pass
            return True

        except (ValueError, AttributeError):
            return False
