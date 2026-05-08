"""Tests for helper field descriptions."""

from openhab_semantic_mcp.helpers.descriptions import (
    FILTERS_DESCRIPTION,
    FILTERS_DESCRIPTION_MONITORING,
    REFINEMENT_DESCRIPTION,
)


def test_descriptions_are_populated_and_consistent():
    assert "ambiguity" in REFINEMENT_DESCRIPTION
    assert "DO NOT invent or guess item names" in REFINEMENT_DESCRIPTION
    assert FILTERS_DESCRIPTION == "Standard semantic search filters"
    assert "event detection" in FILTERS_DESCRIPTION_MONITORING
