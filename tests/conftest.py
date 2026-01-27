"""Pytest configuration and fixtures."""

import pytest
from openhab_semantic_mcp.dto import State, Location, Equipment, Item


@pytest.fixture
def sample_state():
    """Create a sample state for testing."""
    return State(value="21.5 °C")


@pytest.fixture
def sample_location():
    """Create a sample location for testing."""
    return Location(name="Indoor_Room_LivingRoom", label="Living Room")


@pytest.fixture
def sample_equipment():
    """Create a sample equipment for testing."""
    return Equipment(
        type="Lighting_Ceiling",
        id="CeilingLight_LivingRoom",
        label="Living Room Ceiling Light"
    )


@pytest.fixture
def sample_item(sample_state, sample_location, sample_equipment):
    """Create a sample item for testing."""
    return Item(
        name="LivingRoom_Temperature",
        type="Number",
        state=sample_state,
        label="Living Room Temperature",
        location=sample_location,
        equipment=sample_equipment,
        point="Measurement",
        property="Temperature"
    )


@pytest.fixture
def hierarchical_location():
    """Create a hierarchical location structure."""
    house = Location(name="House", label="House")
    indoor = Location(name="Indoor", label="Indoor", parent=house)
    living_room = Location(name="Indoor_Room_LivingRoom", label="Living Room", parent=indoor)
    return living_room


@pytest.fixture
def hierarchical_equipment():
    """Create a hierarchical equipment structure."""
    main_lighting = Equipment(type="Lighting", id="MainLighting", label="Main Lighting")
    ceiling_lighting = Equipment(
        type="Lighting_Ceiling",
        id="CeilingLighting",
        label="Ceiling Lighting", 
        parent=main_lighting
    )
    downlight = Equipment(
        type="Lighting_Ceiling_Downlight",
        id="Downlight1",
        label="Downlight 1",
        parent=ceiling_lighting
    )
    return downlight


@pytest.fixture
def complex_items(hierarchical_location, hierarchical_equipment):
    """Create a set of complex items for testing."""
    return [
        Item(
            name="LivingRoom_Temperature",
            type="Number",
            state=State(value="21.5 °C"),
            location=hierarchical_location,
            equipment=hierarchical_equipment,
            point="Measurement",
            property="Temperature"
        ),
        Item(
            name="LivingRoom_Light",
            type="Switch",
            state=State(value="ON"),
            location=hierarchical_location,
            equipment=hierarchical_equipment,
            point="Control",
            property="Light"
        ),
        Item(
            name="Garden_Temperature",
            type="Number",
            state=State(value="18.2 °C"),
            location=Location(name="Outdoor_Garden", label="Garden"),
            point="Measurement",
            property="Temperature"
        ),
        Item(
            name="Garden_Light",
            type="Switch",
            state=State(value="OFF"),
            location=Location(name="Outdoor_Garden", label="Garden"),
            point="Control",
            property="Light"
        )
    ]
