"""Data Transfer Objects for openHAB semantic models.

This module defines Pydantic models for openHAB items, states, locations,
equipment, and other semantic entities used throughout the MCP server.
"""

from typing import Optional
from pydantic import BaseModel, Field


class State(BaseModel):
    """Represents an openHAB item state with value and metadata."""

    value: str
    display_state: Optional[str] = None
    state_type: Optional[str] = Field(None, alias="type")
    numeric_state: Optional[float] = Field(None, alias="numericState")
    unit: Optional[str] = None

    class Config:
        """Pydantic configuration for State model."""

        populate_by_name = True


class Location(BaseModel):
    """Represents openHAB Location with hierarchical relationships."""

    name: str
    label: Optional[str] = None
    parent: Optional["Location"] = None
    short_name: str  # LLM-friendly name (e.g., "LivingRoom") - REQUIRED!

    class Config:
        """Pydantic configuration for Location model."""

        populate_by_name = True
        arbitrary_types_allowed = True


class Equipment(BaseModel):
    """Represents openHAB Equipment with type, metadata, and parent relationships."""

    type: str
    id: str
    label: Optional[str] = None
    parent: Optional["Equipment"] = None
    short_name: str  # LLM-friendly name (e.g., "Downlight") - REQUIRED!

    class Config:
        """Pydantic configuration for Equipment model."""

        populate_by_name = True
        arbitrary_types_allowed = True


class Item(BaseModel):
    """Represents an openHAB item with semantic metadata."""

    name: str
    label: Optional[str] = None
    type: str
    state: Optional[State] = None
    location: Optional[Location] = None
    equipment: Optional[Equipment] = None
    point: Optional[str] = None
    property: Optional[str] = None
    read_only: Optional[bool] = None
    allowed_commands: Optional[list[str]] = None
    allowed_states: Optional[list[str]] = None

    class Config:
        """Pydantic configuration for Item model."""

        populate_by_name = True
        arbitrary_types_allowed = True
