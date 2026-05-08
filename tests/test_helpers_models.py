"""Tests for helper filter models."""

import pytest

from openhab_semantic_mcp.helpers.models import (
    ExactStateSelection,
    ItemRefinement,
    RangeStateSelection,
    SearchFilters,
)


def test_search_filters_coerces_string_state_to_exact_selection():
    filters = SearchFilters(state="ON")

    assert isinstance(filters.state, ExactStateSelection)
    assert filters.state.kind == "exact"
    assert filters.state.states == ["ON"]


def test_search_filters_coerces_list_state_to_exact_selection():
    filters = SearchFilters(state=["ON", "OFF"])

    assert isinstance(filters.state, ExactStateSelection)
    assert filters.state.states == ["ON", "OFF"]


def test_search_filters_supports_range_state_selection():
    filters = SearchFilters(
        state={
            "kind": "range",
            "lowerBound": 20.0,
            "upperBound": 25.0,
            "includeLower": False,
            "includeUpper": True,
        }
    )

    assert isinstance(filters.state, RangeStateSelection)
    assert filters.state.lowerBound == 20.0
    assert filters.state.upperBound == 25.0
    assert filters.state.includeLower is False
    assert filters.state.includeUpper is True


def test_range_state_selection_rejects_unknown_fields():
    with pytest.raises(Exception):
        SearchFilters(
            state={
                "kind": "range",
                "lowerBound": 10.0,
                "upperBound": 15.0,
                "unexpected": "value",
            }
        )


def test_item_refinement_model_accepts_item_names():
    refinement = ItemRefinement(item_names=["LivingRoom_Light", "Kitchen_Light"])

    assert refinement.item_names == ["LivingRoom_Light", "Kitchen_Light"]
