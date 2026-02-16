"""Tests for inventory indexing and hierarchical queries."""

from openhab_semantic_mcp.inventory import Inventory, ExactStateFilter
from openhab_semantic_mcp.dto import Item, State, Location, Equipment


class TestInventoryIndexing:
    """Test inventory indexing with hierarchical relationships."""

    def setup_method(self):
        """Set up test inventory with sample items."""
        self.inventory = Inventory()

        # Create test locations with hierarchy
        self.living_room = Location(
            name="Indoor_Room_LivingRoom", label="Living Room", short_name="LivingRoom"
        )
        self.kitchen = Location(
            name="Indoor_Room_Kitchen", label="Kitchen", short_name="Kitchen"
        )
        self.garden = Location(
            name="Outdoor_Garden", label="Garden", short_name="Garden"
        )

        # Create test equipment with hierarchy
        self.ceiling_light = Equipment(
            type="Lighting_Ceiling",
            id="CeilingLight_LivingRoom",
            label="Living Room Ceiling Light",
            short_name="CeilingLight",
        )
        self.wall_light = Equipment(
            type="Lighting_Wall",
            id="WallLight_LivingRoom",
            label="Living Room Wall Light",
            parent=self.ceiling_light,  # Parent relationship
            short_name="WallLight",
        )

        # Create test items
        self.items = [
            Item(
                name="LivingRoom_Temperature",
                type="Number",
                state=State(value="21.5 °C"),
                location=self.living_room,
                equipment=self.ceiling_light,
                point="Measurement",
                property="Temperature",
            ),
            Item(
                name="LivingRoom_Light",
                type="Switch",
                state=State(value="ON"),
                location=self.living_room,
                equipment=self.wall_light,
                point="Control",
                property="Light",
            ),
            Item(
                name="Kitchen_Temperature",
                type="Number",
                state=State(value="22.0 °C"),
                location=self.kitchen,
                point="Measurement",
                property="Temperature",
            ),
            Item(
                name="Garden_Light",
                type="Switch",
                state=State(value="OFF"),
                location=self.garden,
                point="Control",
                property="Light",
            ),
        ]

        self.inventory.initialize_inventory(self.items)

    def test_basic_indexing(self):
        """Test basic indexing functionality."""
        # Test location indexing
        living_room_items = self.inventory.get(location="Indoor_Room_LivingRoom")
        assert len(living_room_items) == 2
        assert "LivingRoom_Temperature" in living_room_items
        assert "LivingRoom_Light" in living_room_items

        # Test equipment indexing
        lighting_items = self.inventory.get(equipment="Lighting")
        assert len(lighting_items) == 2

        # Test point indexing
        measurement_items = self.inventory.get(point="Measurement")
        assert len(measurement_items) == 2
        assert "LivingRoom_Temperature" in measurement_items
        assert "Kitchen_Temperature" in measurement_items

    def test_location_type_hierarchy(self):
        """Test location type hierarchy queries."""
        # Query by top-level type
        indoor_items = self.inventory.get(location="Indoor")
        assert len(indoor_items) == 3  # Living room + kitchen items

        outdoor_items = self.inventory.get(location="Outdoor")
        assert len(outdoor_items) == 1  # Garden items

        # Query by mid-level type (Indoor_Room exists due to string hierarchy)
        indoor_room_items = self.inventory.get(location="Indoor_Room")
        assert len(indoor_room_items) == 3  # Living room + kitchen items

        # Query by specific type
        living_room_items = self.inventory.get(location="Indoor_Room_LivingRoom")
        assert len(living_room_items) == 2  # Living room items only

        # Query by kitchen specifically
        kitchen_items = self.inventory.get(location="Indoor_Room_Kitchen")
        assert len(kitchen_items) == 1  # Kitchen items only

    def test_equipment_type_hierarchy(self):
        """Test equipment type hierarchy queries."""
        # Query by top-level type
        lighting_items = self.inventory.get(equipment="Lighting")
        assert len(lighting_items) == 2

        # Query by specific type
        ceiling_items = self.inventory.get(equipment="Lighting_Ceiling")
        assert len(ceiling_items) == 2  # Both items under ceiling light

        wall_items = self.inventory.get(equipment="Lighting_Wall")
        assert len(wall_items) == 1  # Only wall light item

    def test_equipment_parent_hierarchy(self):
        """Test equipment parent relationships."""
        # Items under parent equipment should be found when querying parent
        parent_items = self.inventory.get(equipment="Lighting_Ceiling")
        assert len(parent_items) == 2  # Both ceiling and wall light items

        # Child equipment should only find its direct items
        child_items = self.inventory.get(equipment="Lighting_Wall")
        assert len(child_items) == 1  # Only wall light item

    def test_point_hierarchy(self):
        """Test point type hierarchy queries."""
        # Test point hierarchy (if points have hierarchical names)
        measurement_items = self.inventory.get(point="Measurement")
        assert len(measurement_items) == 2

        control_items = self.inventory.get(point="Control")
        assert len(control_items) == 2

    def test_property_hierarchy(self):
        """Test property type hierarchy queries."""
        temperature_items = self.inventory.get(item_property="Temperature")
        assert len(temperature_items) == 2

        light_items = self.inventory.get(item_property="Light")
        assert len(light_items) == 2

    def test_type_indexing(self):
        """Test item type indexing."""
        number_items = self.inventory.get(item_type="Number")
        assert len(number_items) == 2

        switch_items = self.inventory.get(item_type="Switch")
        assert len(switch_items) == 2

    def test_combined_filters(self):
        """Test combining multiple filters."""
        # Location + Point
        living_room_measurements = self.inventory.get(
            location="Indoor_Room_LivingRoom", point="Measurement"
        )
        assert len(living_room_measurements) == 1
        assert "LivingRoom_Temperature" in living_room_measurements

        # Equipment + Property
        lighting_light = self.inventory.get(equipment="Lighting", item_property="Light")
        assert len(lighting_light) == 1
        assert "LivingRoom_Light" in lighting_light

    def test_invert_selection(self):
        """Test invert selection functionality."""
        # Invert location selection
        non_living_room = self.inventory.get(
            location="Indoor_Room_LivingRoom", invert_selection={"location"}
        )
        assert len(non_living_room) == 2  # Kitchen + Garden items

        # Invert equipment selection
        non_lighting = self.inventory.get(
            equipment="Lighting", invert_selection={"equipment"}
        )
        assert len(non_lighting) == 2  # Non-lighting items

    def test_available_types(self):
        """Test getting available types."""
        locations = self.inventory.get_available_locations()
        assert "Indoor_Room_LivingRoom" in locations
        assert "Indoor_Room_Kitchen" in locations
        assert "Outdoor_Garden" in locations

        equipment = self.inventory.get_available_equipment()
        assert "Lighting_Ceiling" in equipment
        assert "Lighting_Wall" in equipment

        types = self.inventory.get_available_types()
        assert "Number" in types
        assert "Switch" in types

    def test_state_filtering(self):
        """Test state-based filtering."""
        on_items = self.inventory.get(state=ExactStateFilter(states=["ON"]))
        assert len(on_items) == 1
        assert "LivingRoom_Light" in on_items

        off_items = self.inventory.get(state=ExactStateFilter(states=["OFF"]))
        assert len(off_items) == 1
        assert "Garden_Light" in off_items
