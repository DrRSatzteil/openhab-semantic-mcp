"""Tests for helper item utility functions."""

import pytest

from openhab_semantic_mcp.dto import Equipment, Item, Location, State
from openhab_semantic_mcp.exceptions import InvalidFilterError
from openhab_semantic_mcp.helpers.items import (
    convert_state_selection,
    format_item_response,
    validate_filter_values,
)
from openhab_semantic_mcp.helpers.models import (
    ExactStateSelection,
    RangeStateSelection,
    SearchFilters,
)
from openhab_semantic_mcp.inventory import ExactStateFilter, Inventory, RangeStateFilter


@pytest.fixture
def sample_inventory():
    inventory = Inventory()
    location = Location(name="Indoor_Room_LivingRoom", label="Living Room", short_name="LivingRoom")
    equipment = Equipment(type="Lighting_Ceiling", id="CeilingLight", label="Ceiling Light", short_name="Ceiling")

    items = [
        Item(
            name="LivingRoom_Light",
            type="Switch",
            state=State(value="ON"),
            location=location,
            equipment=equipment,
            point="Control",
            property="Light",
        ),
        Item(
            name="LivingRoom_Temperature",
            type="Number",
            state=State(value="21.3"),
            location=location,
            point="Measurement",
            property="Temperature",
        ),
    ]
    inventory.initialize_inventory(items)
    return inventory


def test_convert_state_selection_returns_none_for_empty_input():
    assert convert_state_selection(None) is None


def test_convert_state_selection_converts_exact_selection():
    converted = convert_state_selection(ExactStateSelection(states=["ON", "OFF"]))

    assert isinstance(converted, ExactStateFilter)
    assert converted.states == ["ON", "OFF"]


def test_convert_state_selection_converts_range_selection():
    converted = convert_state_selection(
        RangeStateSelection(
            lowerBound=10.0,
            upperBound=20.0,
            includeLower=False,
            includeUpper=True,
        )
    )

    assert isinstance(converted, RangeStateFilter)
    assert converted.lower == 10.0
    assert converted.upper == 20.0
    assert converted.include_lower is False
    assert converted.include_upper is True


def test_validate_filter_values_accepts_existing_values(sample_inventory):
    filters = SearchFilters(
        location="Indoor_Room_LivingRoom",
        equipment="Lighting_Ceiling",
        point="Control",
        property="Light",
    )

    assert validate_filter_values(sample_inventory, filters) is None


def test_validate_filter_values_returns_none_when_filters_not_provided(sample_inventory):
    assert validate_filter_values(sample_inventory, None) is None


def test_validate_filter_values_raises_with_guidance_for_invalid_values(sample_inventory):
    filters = SearchFilters(
        location="Indoor_Room_Kitchen",
        equipment="HVAC",
        point="Setpoint",
        property="Humidity",
    )

    with pytest.raises(InvalidFilterError) as exc_info:
        validate_filter_values(sample_inventory, filters)

    error = exc_info.value
    assert error.error_code == "INVALID_FILTER"
    assert error.filter_name == "multiple_filters"
    assert "Use get_available_semantic_entities() first" in error.guidance["suggestion"]
    assert len(error.guidance["available_locations"]) <= 10
    assert len(error.guidance["available_equipment"]) <= 10


def test_format_item_response_builds_location_and_equipment_hierarchy():
    house = Location(name="Indoor", label="Indoor", short_name="Indoor")
    room = Location(
        name="Indoor_Room_LivingRoom",
        label="Living Room",
        short_name="LivingRoom",
        parent=house,
    )

    parent_equipment = Equipment(
        type="Lighting",
        id="MainLighting",
        label="Main Lighting",
        short_name="MainLighting",
    )
    child_equipment = Equipment(
        type="Lighting_Ceiling",
        id="CeilingLight",
        label="Ceiling Light",
        short_name="Ceiling",
        parent=parent_equipment,
    )

    item = Item(
        name="LivingRoom_Light",
        type="Switch",
        state=State(value="ON"),
        location=room,
        equipment=child_equipment,
        point="Control",
        property="Light",
        allowed_commands=["ON", "OFF"],
        allowed_states=["ON", "OFF"],
    )

    response = format_item_response(item)

    assert response["name"] == "LivingRoom_Light"
    assert response["state"] == "ON"
    assert response["location"]["hierarchy"] == ["Indoor", "Indoor_Room_LivingRoom"]
    assert response["equipment"]["type"] == "Lighting_Ceiling"
    assert response["equipment"]["parent"]["type"] == "Lighting"


def test_format_item_response_includes_command_and_state_labels():
    item = Item(
        name="vacuum_livingroom_segment",
        type="String",
        allowed_commands=["16", "17", "18"],
        allowed_states=["16", "17", "18"],
        command_labels={"16": "Esszimmer", "17": "Wohnzimmer", "18": "WC"},
        state_labels={"16": "Esszimmer", "17": "Wohnzimmer", "18": "WC"},
    )

    response = format_item_response(item)

    assert response["command_labels"] == {"16": "Esszimmer", "17": "Wohnzimmer", "18": "WC"}
    assert response["state_labels"] == {"16": "Esszimmer", "17": "Wohnzimmer", "18": "WC"}


def test_format_item_response_labels_default_to_none():
    item = Item(name="switch1", type="Switch", allowed_commands=["ON", "OFF"])

    response = format_item_response(item)

    assert response["command_labels"] is None
    assert response["state_labels"] is None
