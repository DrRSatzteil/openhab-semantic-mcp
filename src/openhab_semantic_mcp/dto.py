"""Data Transfer Objects for OpenHAB semantic models.

This module defines Pydantic models for OpenHAB items, states, locations,
equipment, and other semantic entities used throughout the MCP server.
"""

from typing import Optional
from pydantic import BaseModel, Field


class State(BaseModel):
    """Represents an OpenHAB item state with value and metadata."""

    value: str
    display_state: Optional[str] = None
    state_type: Optional[str] = Field(None, alias="type")
    numeric_state: Optional[float] = Field(None, alias="numericState")
    unit: Optional[str] = None

    class Config:
        """Pydantic configuration for State model."""

        populate_by_name = True


class Location(BaseModel):
    """Represents OpenHAB Location with hierarchical relationships."""

    name: str
    label: Optional[str] = None
    parent: Optional["Location"] = None
    short_name: str  # LLM-friendly name (e.g., "LivingRoom") - REQUIRED!

    class Config:
        """Pydantic configuration for Location model."""

        populate_by_name = True
        arbitrary_types_allowed = True


class Equipment(BaseModel):
    """Represents OpenHAB Equipment with type, metadata, and parent relationships."""

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
    """Represents an OpenHAB item with semantic metadata."""

    name: str
    label: Optional[str] = None
    type: str
    state: Optional[State] = None
    location: Optional[Location] = None
    equipment: Optional[Equipment] = None
    point: Optional[str] = None
    property: Optional[str] = None
    read_only: Optional[bool] = None

    class Config:
        """Pydantic configuration for Item model."""

        populate_by_name = True
        arbitrary_types_allowed = True
