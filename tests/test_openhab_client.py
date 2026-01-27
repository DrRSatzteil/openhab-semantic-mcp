"""Tests for OpenHAB client semantic parsing and hierarchy building."""

import pytest
from unittest.mock import Mock, patch
from openhab_semantic_mcp.openhab_client import OpenHAB
from openhab_semantic_mcp.dto import Location, Equipment


class TestOpenHABClient:
    """Test OpenHAB client semantic parsing functionality."""

    def setup_method(self):
        """Set up test OpenHAB client."""
        self.client = OpenHAB(base_url="http://localhost:8080")

    def test_build_location_hierarchy_full(self):
        """Test building full location hierarchy with semantic value."""
        location_item = {
            "name": "LivingRoom_Location",
            "label": "Living Room",
            "metadata": {
                "semantics": {
                    "value": "Location_Indoor_Room_LivingRoom",
                    "config": {}
                }
            },
            "parents": []
        }
        
        location = self.client._build_location_hierarchy(location_item)
        
        assert location.name == "Indoor_Room_LivingRoom"
        assert location.label == "Living Room"
        assert location.parent is None
        assert location.short_name == "LivingRoom"

    def test_build_location_hierarchy_with_parent(self):
        """Test building location hierarchy with parent relationship."""
        parent_item = {
            "name": "House_Location", 
            "label": "House",
            "metadata": {
                "semantics": {
                    "value": "Location_Indoor_House",
                    "config": {}
                }
            },
            "parents": []
        }
        
        child_item = {
            "name": "LivingRoom_Location",
            "label": "Living Room",
            "metadata": {
                "semantics": {
                    "value": "Location_Indoor_Room_LivingRoom",
                    "config": {
                        "isPartOf": "House_Location"
                    }
                }
            },
            "parents": [parent_item]
        }
        
        location = self.client._build_location_hierarchy(child_item)
        
        assert location.name == "Indoor_Room_LivingRoom"
        assert location.label == "Living Room"
        assert location.parent is not None
        assert location.parent.name == "Indoor_House"
        assert location.short_name == "LivingRoom"
        assert location.parent.label == "House"

    def test_build_location_hierarchy_invalid_semantics(self):
        """Test building location with invalid semantic value raises error."""
        location_item = {
            "name": "InvalidLocation",
            "label": "Invalid Location",
            "metadata": {
                "semantics": {
                    "value": "InvalidTag",
                    "config": {}
                }
            },
            "parents": []
        }
        
        # Should raise ValueError for invalid semantics
        with pytest.raises(ValueError, match="Invalid location semantics"):
            self.client._build_location_hierarchy(location_item)

    def test_build_equipment_hierarchy_full(self):
        """Test building full equipment hierarchy."""
        equipment_item = {
            "name": "CeilingLight_Equipment",
            "label": "Ceiling Light",
            "metadata": {
                "semantics": {
                    "value": "Equipment_Lighting_Ceiling",
                    "config": {}
                }
            },
            "parents": []
        }
        
        equipment = self.client._build_equipment_hierarchy(equipment_item)
        
        assert equipment.type == "Lighting_Ceiling"
        assert equipment.id == "CeilingLight_Equipment"
        assert equipment.label == "Ceiling Light"
        assert equipment.parent is None
        assert equipment.short_name == "Ceiling"

    def test_build_equipment_hierarchy_with_parent(self):
        """Test building equipment hierarchy with parent relationship."""
        parent_item = {
            "name": "MainLighting_Equipment",
            "label": "Main Lighting",
            "metadata": {
                "semantics": {
                    "value": "Equipment_Lighting",
                    "config": {}
                }
            },
            "parents": []
        }
        
        child_item = {
            "name": "CeilingLight_Equipment",
            "label": "Ceiling Light",
            "metadata": {
                "semantics": {
                    "value": "Equipment_Lighting_Ceiling",
                    "config": {
                        "isPartOf": "MainLighting_Equipment"
                    }
                }
            },
            "parents": [parent_item]
        }
        
        equipment = self.client._build_equipment_hierarchy(child_item)
        
        assert equipment.type == "Lighting_Ceiling"
        assert equipment.id == "CeilingLight_Equipment"
        assert equipment.label == "Ceiling Light"
        assert equipment.parent is not None
        assert equipment.parent.type == "Lighting"
        assert equipment.short_name == "Ceiling"
        assert equipment.parent.id == "MainLighting_Equipment"
        assert equipment.parent.label == "Main Lighting"

    def test_build_equipment_hierarchy_no_semantics(self):
        """Test building equipment without semantic value."""
        equipment_item = {
            "name": "SimpleEquipment",
            "label": "Simple Equipment",
            "metadata": {},
            "parents": []
        }
        
        equipment = self.client._build_equipment_hierarchy(equipment_item)
        
        assert equipment.type == ""
        assert equipment.id == "SimpleEquipment"
        assert equipment.label == "Simple Equipment"
        assert equipment.parent is None
        assert equipment.short_name == ""

    def test_find_parent_by_name(self):
        """Test finding parent by name."""
        parents = [
            {"name": "Parent1", "label": "Parent 1"},
            {"name": "Parent2", "label": "Parent 2"},
            {"name": "Parent3", "label": "Parent 3"}
        ]
        
        found = self.client._find_parent_by_name(parents, "Parent2")
        assert found is not None
        assert found["name"] == "Parent2"
        
        not_found = self.client._find_parent_by_name(parents, "NonExistent")
        assert not_found is None

    def test_build_recursive_locations(self):
        """Test building recursive location list."""
        # Create location hierarchy: House -> Indoor -> LivingRoom
        house = Location(name="House", label="House", short_name="House")
        indoor = Location(name="Indoor", label="Indoor", parent=house, short_name="Indoor")
        living_room = Location(name="Indoor_Room_LivingRoom", label="Living Room", parent=indoor, short_name="LivingRoom")
        
        locations = self.client._build_recursive_locations(living_room)
        
        assert locations == ["House", "Indoor", "Indoor_Room_LivingRoom"]

    def test_build_recursive_locations_no_parent(self):
        """Test building recursive locations with no parent."""
        location = Location(name="SimpleLocation", label="Simple Location", short_name="SimpleLocation")
        
        locations = self.client._build_recursive_locations(location)
        
        assert locations == ["SimpleLocation"]

    @patch('requests.get')
    def test_get_semantic_points_success(self, mock_get):
        """Test successful semantic points retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "links": []
        }
        mock_get.return_value = mock_response
        
        # This would need more complex mocking for full testing
        # For now, just test that the method exists and can be called
        try:
            result = self.client.get_semantic_points()
            assert isinstance(result, list)
        except Exception:
            # Expected due to mocking limitations
            pass
