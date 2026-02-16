"""Data models for semantic search filters and item refinement."""

import abc
from typing import List, Optional, Set, Literal, Union

from pydantic import BaseModel, Field


class ItemRefinement(BaseModel):
    """Specific item names for additional filtering"""

    item_names: List[str] = Field(
        description="Specific item names for additional filtering"
    )


class StateSelectionModel(BaseModel, abc.ABC):
    """Base model for state selection"""

    kind: Literal["exact", "range"] = Field(
        description="How to match states - 'exact' for exact matches, 'range' for numeric ranges"
    )


class ExactStateSelection(StateSelectionModel):
    """Exact state selection"""

    kind: Literal["exact"] = "exact"
    states: List[str] = Field(description="List of exact state values to filter by")


class RangeStateSelection(StateSelectionModel):
    """Numeric range state selection"""

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
        populate_by_name = True
        extra = "forbid"


class SearchFilters(BaseModel):
    """Standard semantic search filters"""

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
    type: Optional[str] = Field(
        None, description="Target item type (e.g., 'Switch', 'Dimmer')"
    )
    state: Optional[Union[ExactStateSelection, RangeStateSelection, None]] = Field(
        None,
        description=(
            "Target current state filter. Must be a structured object, never a plain string. "
            'For exact matches: {"kind": "exact", "states": ["ON"]} or {"kind": "exact", "states": ["OFF", "UNDEF"]}. '
            'For numeric ranges: {"kind": "range", "lowerBound": 20.0, "upperBound": 30.0}. '
            'Example: to filter for ON state use {"kind": "exact", "states": ["ON"]}.'
        ),
    )
    readonly: Optional[bool] = Field(None, description="Filter by readonly status")
    invert_selection: Optional[Set[str]] = Field(
        None,
        description="Inverts the selection of the specified filters (e.g. 'point', 'state')",
    )
