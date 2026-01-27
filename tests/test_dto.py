"""Tests for DTO models and their relationships."""

import pytest
from openhab_semantic_mcp.dto import State, Location, Equipment, Item


class TestDTOModels:
    """Test DTO model creation and relationships."""

    def test_state_creation(self):
        """Test State model creation."""
        state = State(value="21.5 °C")
        
        assert state.value == "21.5 °C"
        assert state.display_state is None
        assert state.unit is None

    def test_state_with_all_fields(self):
        """Test State model with all fields."""
        state = State(
            value="21.5",
            display_state="21.5 °C",
            state_type="Number",
            numericState=21.5,
            unit="°C"
        )
        
        assert state.value == "21.5"
        assert state.display_state == "21.5 °C"
        assert state.state_type == "Number"
        assert state.numeric_state == 21.5
        assert state.unit == "°C"

    def test_location_creation(self):
        """Test Location model creation."""
        location = Location(name="Indoor_Room_LivingRoom", label="Living Room")
        
        assert location.name == "Indoor_Room_LivingRoom"
        assert location.label == "Living Room"
        assert location.parent is None

    def test_location_with_parent(self):
        """Test Location model with parent relationship."""
        parent = Location(name="Indoor", label="Indoor")
        child = Location(
            name="Indoor_Room_LivingRoom", 
            label="Living Room",
            parent=parent
        )
        
        assert child.name == "Indoor_Room_LivingRoom"
        assert child.label == "Living Room"
        assert child.parent is parent
        assert child.parent.name == "Indoor"

    def test_location_recursive_hierarchy(self):
        """Test recursive location hierarchy."""
        house = Location(name="House", label="House")
        indoor = Location(name="Indoor", label="Indoor", parent=house)
        living_room = Location(name="Indoor_Room_LivingRoom", label="Living Room", parent=indoor)
        
        assert living_room.parent is indoor
        assert living_room.parent.parent is house
        assert living_room.parent.parent.parent is None

    def test_equipment_creation(self):
        """Test Equipment model creation."""
        equipment = Equipment(
            type="Lighting_Ceiling",
            id="CeilingLight_LivingRoom",
            label="Living Room Ceiling Light"
        )
        
        assert equipment.type == "Lighting_Ceiling"
        assert equipment.id == "CeilingLight_LivingRoom"
        assert equipment.label == "Living Room Ceiling Light"
        assert equipment.parent is None

    def test_equipment_with_parent(self):
        """Test Equipment model with parent relationship."""
        parent = Equipment(type="Lighting", id="MainLighting", label="Main Lighting")
        child = Equipment(
            type="Lighting_Ceiling",
            id="CeilingLight_LivingRoom", 
            label="Living Room Ceiling Light",
            parent=parent
        )
        
        assert child.type == "Lighting_Ceiling"
        assert child.id == "CeilingLight_LivingRoom"
        assert child.label == "Living Room Ceiling Light"
        assert child.parent is parent
        assert child.parent.type == "Lighting"

    def test_equipment_recursive_hierarchy(self):
        """Test recursive equipment hierarchy."""
        main_lighting = Equipment(type="Lighting", id="MainLighting", label="Main Lighting")
        ceiling_lighting = Equipment(
            type="Lighting_Ceiling", 
            id="CeilingLighting", 
            label="Ceiling Lighting",
            parent=main_lighting
        )
        specific_light = Equipment(
            type="Lighting_Ceiling_Downlight",
            id="Downlight1",
            label="Downlight 1", 
            parent=ceiling_lighting
        )
        
        assert specific_light.parent is ceiling_lighting
        assert specific_light.parent.parent is main_lighting
        assert specific_light.parent.parent.parent is None

    def test_item_creation_minimal(self):
        """Test Item model creation with minimal fields."""
        state = State(value="ON")
        item = Item(
            name="TestLight",
            type="Switch",
            state=state
        )
        
        assert item.name == "TestLight"
        assert item.type == "Switch"
        assert item.state is state
        assert item.label is None
        assert item.location is None
        assert item.equipment is None
        assert item.point is None
        assert item.property is None

    def test_item_creation_full(self):
        """Test Item model creation with all fields."""
        state = State(value="21.5 °C")
        location = Location(name="Indoor_Room_LivingRoom", label="Living Room")
        equipment = Equipment(type="Lighting_Ceiling", id="CeilingLight", label="Ceiling Light")
        
        item = Item(
            name="LivingRoom_Temperature",
            type="Number",
            state=state,
            label="Living Room Temperature",
            read_only=False,
            location=location,
            equipment=equipment,
            point="Measurement",
            property="Temperature"
        )
        
        assert item.name == "LivingRoom_Temperature"
        assert item.type == "Number"
        assert item.state is state
        assert item.label == "Living Room Temperature"
        assert item.read_only is False
        assert item.location is location
        assert item.equipment is equipment
        assert item.point == "Measurement"
        assert item.property == "Temperature"

    def test_item_with_recursive_locations(self):
        """Test item with recursive location relationships."""
        house = Location(name="House", label="House")
        indoor = Location(name="Indoor", label="Indoor", parent=house)
        living_room = Location(name="Indoor_Room_LivingRoom", label="Living Room", parent=indoor)
        
        state = State(value="ON")
        item = Item(
            name="LivingRoom_Light",
            type="Switch",
            state=state,
            location=living_room
        )
        
        # Test that we can traverse the location hierarchy
        assert item.location.name == "Indoor_Room_LivingRoom"
        assert item.location.parent.name == "Indoor"
        assert item.location.parent.parent.name == "House"
        assert item.location.parent.parent.parent is None

    def test_item_with_recursive_equipment(self):
        """Test item with recursive equipment relationships."""
        main_lighting = Equipment(type="Lighting", id="MainLighting", label="Main Lighting")
        ceiling_lighting = Equipment(
            type="Lighting_Ceiling",
            id="CeilingLighting", 
            label="Ceiling Lighting",
            parent=main_lighting
        )
        
        state = State(value="ON")
        item = Item(
            name="CeilingLight1",
            type="Switch",
            state=state,
            equipment=ceiling_lighting
        )
        
        # Test that we can traverse the equipment hierarchy
        assert item.equipment.type == "Lighting_Ceiling"
        assert item.equipment.parent.type == "Lighting"
        assert item.equipment.parent.parent is None

    def test_model_serialization(self):
        """Test that models can be serialized to dict."""
        state = State(value="21.5 °C")
        location = Location(name="Indoor_Room_LivingRoom", label="Living Room")
        
        # Test model dict conversion
        state_dict = state.model_dump()
        assert state_dict["value"] == "21.5 °C"
        
        location_dict = location.model_dump()
        assert location_dict["name"] == "Indoor_Room_LivingRoom"
        assert location_dict["label"] == "Living Room"
