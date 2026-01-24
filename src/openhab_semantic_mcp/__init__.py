"""
OpenHAB Semantic MCP Server

A lightweight MCP (Model Context Protocol) server for OpenHAB semantic operations.

This package provides tools for:
- Sending commands to OpenHAB items
- Getting item information from the semantic inventory
- Querying items by location, equipment, points, and properties
- Real-time state updates via SSE
"""

__version__ = "0.1.0"
__author__ = "Thomas Lauterbach"
__email__ = "drrsatzteil@web.de"

from .openhab_client import OpenHAB
from .inventory import Inventory
from .dto import State

__all__ = [
    "OpenHAB",
    "Inventory",
    "State",
]
