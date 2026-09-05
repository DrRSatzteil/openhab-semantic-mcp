"""Tests for helper item operation execution."""

from unittest.mock import Mock

import pytest

from openhab_semantic_mcp.dto import Item
from openhab_semantic_mcp.exceptions import ValidationError
from openhab_semantic_mcp.helpers.models import ItemRefinement, SearchFilters
from openhab_semantic_mcp.helpers.operations import execute_item_operation


def _make_item(
    name: str,
    *,
    read_only: bool = False,
    allowed_commands=None,
    allowed_states=None,
    command_labels=None,
    state_labels=None,
):
    return Item(
        name=name,
        type="Switch",
        label=name,
        read_only=read_only,
        allowed_commands=allowed_commands,
        allowed_states=allowed_states,
        command_labels=command_labels,
        state_labels=state_labels,
    )


@pytest.mark.asyncio
async def test_execute_item_operation_command_success_without_filters():
    openhab = Mock()
    openhab.send_command.return_value = {"success": True}

    inventory = Mock()
    inventory.get.return_value = {"LivingRoom_Light"}
    inventory.get_item.return_value = _make_item(
        "LivingRoom_Light", allowed_commands=["ON", "OFF"]
    )

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=None,
        refinement=None,
        operation_type="command",
        value="ON",
    )

    assert result["success"] is True
    assert result["items_targeted"] == 1
    assert result["successful_operations"] == 1
    assert result["results"][0]["item_name"] == "LivingRoom_Light"
    assert result["results"][0]["command"] == "ON"
    openhab.send_command.assert_called_once_with("LivingRoom_Light", "ON")


@pytest.mark.asyncio
async def test_execute_item_operation_includes_validation_error_when_no_items_found(monkeypatch):
    openhab = Mock()
    inventory = Mock()
    inventory.get.return_value = set()

    monkeypatch.setattr(
        "openhab_semantic_mcp.helpers.operations.validate_filter_values",
        lambda inv, f: None,
    )

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=SearchFilters(location="Indoor_Room_Bedroom"),
        refinement=ItemRefinement(item_names=["AnyItem"]),
        operation_type="command",
        value="ON",
    )

    assert result["success"] is False
    assert result["error_type"] == "InvalidFilterError"
    assert result["error_code"] == "INVALID_FILTER"
    assert result["operation"] == "command_entities"


@pytest.mark.asyncio
async def test_execute_item_operation_mixed_readonly_and_successful_items(monkeypatch):
    openhab = Mock()
    openhab.send_command.return_value = {"success": True}

    inventory = Mock()
    inventory.get.return_value = {"Readonly_Item", "Writable_Item"}

    items = {
        "Readonly_Item": _make_item(
            "Readonly_Item", read_only=True, allowed_commands=["ON", "OFF"]
        ),
        "Writable_Item": _make_item(
            "Writable_Item", read_only=False, allowed_commands=["ON", "OFF"]
        ),
    }
    inventory.get_item.side_effect = lambda name: items[name]

    monkeypatch.setattr(
        "openhab_semantic_mcp.helpers.operations.validate_filter_values",
        lambda inv, f: None,
    )

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=SearchFilters(location="Indoor_Room_LivingRoom"),
        refinement=None,
        operation_type="command",
        value="ON",
    )

    assert result["items_targeted"] == 2
    assert result["successful_operations"] == 1
    assert result["success"] is True
    assert len(result["results"]) == 2
    assert any(entry["success"] is False for entry in result["results"])
    assert any(entry["success"] is True for entry in result["results"])


@pytest.mark.asyncio
async def test_execute_item_operation_handles_system_level_errors():
    openhab = Mock()
    inventory = Mock()
    inventory.get.side_effect = ConnectionError("openhab unavailable")

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=None,
        refinement=None,
        operation_type="update",
        value="OFF",
    )

    assert result["success"] is False
    assert result["error_type"] == "ConnectionError"
    assert result["operation"] == "update_entities"


@pytest.mark.asyncio
async def test_execute_item_operation_update_covers_invalid_allowed_state_and_backend_failure(
    monkeypatch,
):
    openhab = Mock()
    openhab.post_update.return_value = {"success": False, "error": "Backend rejected update"}

    inventory = Mock()
    inventory.get.return_value = ["Restricted_Item", "Writable_Item"]

    items = {
        "Restricted_Item": _make_item(
            "Restricted_Item", allowed_states=["ON", "OFF"]
        ),
        "Writable_Item": _make_item("Writable_Item"),
    }
    inventory.get_item.side_effect = lambda name: items[name]

    monkeypatch.setattr(
        "openhab_semantic_mcp.helpers.operations.validate_filter_values",
        lambda inv, f: None,
    )

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=SearchFilters(location="Indoor_Room_LivingRoom"),
        refinement=None,
        operation_type="update",
        value="DIM",
    )

    assert result["items_targeted"] == 2
    assert result["successful_operations"] == 0
    assert result["success"] is False
    assert len(result["results"]) == 2
    assert all(entry["success"] is False for entry in result["results"])
    assert any(entry.get("error_type") == "ItemStateError" for entry in result["results"])
    assert any("Backend rejected update" in entry.get("error", "") for entry in result["results"])


@pytest.mark.asyncio
async def test_execute_item_operation_handles_validation_errors_from_inventory_layer():
    openhab = Mock()
    inventory = Mock()
    inventory.get.side_effect = ValidationError("operation_type", "invalid", "Not allowed")

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=None,
        refinement=None,
        operation_type="command",
        value="ON",
    )

    assert result["success"] is False
    assert result["error_type"] == "ValidationError"
    assert result["operation"] == "command_entities"


@pytest.mark.asyncio
async def test_execute_item_operation_command_validation_error_includes_labels(monkeypatch):
    openhab = Mock()
    inventory = Mock()
    inventory.get.return_value = ["vacuum_livingroom_segment"]
    inventory.get_item.return_value = _make_item(
        "vacuum_livingroom_segment",
        allowed_commands=["16", "17", "18"],
        command_labels={"16": "Esszimmer", "17": "Wohnzimmer", "18": "WC"},
    )

    monkeypatch.setattr(
        "openhab_semantic_mcp.helpers.operations.validate_filter_values",
        lambda inv, f: None,
    )

    result = await execute_item_operation(
        openhab=openhab,
        inventory=inventory,
        filters=SearchFilters(location="Indoor_Room_LivingRoom"),
        refinement=None,
        operation_type="command",
        value="99",
    )

    error_entry = result["results"][0]
    assert error_entry["error_type"] == "ItemCommandError"
    assert "16 (Esszimmer)" in error_entry["message"]
    assert "17 (Wohnzimmer)" in error_entry["message"]
    assert "18 (WC)" in error_entry["message"]
