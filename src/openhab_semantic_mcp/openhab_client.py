"""OpenHAB REST API client with SSE support.

This module provides a client for interacting with OpenHAB's REST API,
including fetching semantic items and listening for real-time state updates
via Server-Sent Events (SSE).
"""

import json
import logging
import threading
import time
from typing import List, Optional, Callable

import requests
import sseclient

from .dto import Equipment, Item, Location, State

# Get logger for this module
logger = logging.getLogger(__name__)


class OpenHAB:
    """OpenHAB REST API client with authentication and SSE support."""

    def __init__(
        self,
        base_url: str,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        # Set up authentication
        if api_token:
            self.session.headers.update({"X-OPENHAB-TOKEN": api_token})
        elif username and password:
            self.session.auth = (username, password)

        # SSE related attributes
        self._sse_thread = None
        self._sse_running = False
        self._sse_stop_event = threading.Event()
        self._sse_callback = None

    def get_semantic_points(self) -> List[Item]:
        """Fetch all semantic points from OpenHAB.

        Returns:
            List of Item objects representing semantic points with their metadata
        """

        response = self.session.get(f"{self.base_url}/rest/items?parents=true")
        response.raise_for_status()

        # Process the response
        response_json = response.json()
        processed_items = []

        for item in response_json:
            # Check if item has semantics metadata with Point_* value
            semantics = item.get("metadata", {}).get("semantics", {})
            semantics_value = semantics.get("value", "")

            if semantics_value.startswith("Point_"):
                # Extract semantic information
                config = semantics.get("config", {})

                equipment_name = config.get("isPointOf")

                location_obj = None

                # Check if item has hasLocation in its own semantics
                location_name = config.get("hasLocation")
                if location_name:
                    location_item = self._find_parent_by_name(
                        item.get("parents", []), location_name
                    )
                    if location_item:
                        location_obj, _, _ = self._build_location_hierarchy(location_item)
                # Check for the equipment location instead (recursive)
                elif equipment_name:
                    equipment_item = self._find_parent_by_name(
                        item.get("parents", []), equipment_name
                    )
                    if equipment_item:
                        location_obj = self._find_equipment_location_recursive(
                            equipment_item, item.get("parents", [])
                        )

                equipment = None
                if equipment_name:
                    equipment_item = self._find_parent_by_name(
                        item.get("parents", []), equipment_name
                    )
                    if equipment_item:
                        equipment, _, _ = self._build_equipment_hierarchy(equipment_item)

                # Extract read_only from stateDescription, defaulting to False
                state_description = item.get("stateDescription", {})
                read_only = state_description.get("readOnly", False)

                # Create Item object with all properties
                point = semantics_value.replace("Point_", "")
                property = config.get("relatesTo")
                if property:
                    property = property.replace("Property_", "")

                # Initialize LLM-friendly name fields
                location_name_field = None
                location_full_field = None
                equipment_name_field = None
                equipment_full_field = None
                
                # Set location names if location exists
                if location_obj:
                    location_full_field = location_obj.name
                    # Extract short name from full name
                    location_name_field = location_obj.name.split("_")[-1] if "_" in location_obj.name else location_obj.name
                
                # Set equipment names if equipment exists
                if equipment:
                    equipment_full_field = equipment.type
                    # Extract short name from full type
                    equipment_name_field = equipment.type.split("_")[-1] if "_" in equipment.type else equipment.type

                processed_items.append(
                    Item(
                        name=item["name"],
                        label=item.get("label"),
                        type=item["type"],
                        state=State(value=item["state"]) if item.get("state") else None,
                        location=location_obj,
                        equipment=equipment,
                        point=point if point.strip() else None,
                        property=property if property and property.strip() else None,
                        read_only=read_only,
                        # LLM-friendly name fields
                        location_name=location_name_field,
                        location_full=location_full_field,
                        equipment_name=equipment_name_field,
                        equipment_full=equipment_full_field,
                    )
                )

        return processed_items

    def _build_recursive_locations(self, location_obj: Optional[Location]) -> List[str]:
        """Build recursive list of location names from root to current location"""
        locations = []
        current = location_obj

        while current:
            locations.append(current.name)
            current = current.parent

        return list(reversed(locations))  # Root to current

    def _find_parent_by_name(
        self, parents: List[dict], target_name: str
    ) -> Optional[dict]:
        """Find a parent item by name in the parents list."""
        return next(
            (parent for parent in parents if parent.get("name") == target_name), None
        )

    def _find_equipment_location_recursive(self, equipment_item: dict, all_parents: List[dict]) -> Optional[Location]:
        """Recursively find location for equipment by traversing parent hierarchy.
        
        Args:
            equipment_item: Current equipment item to check
            all_parents: All parents from the original item for searching
            
        Returns:
            Location object if found, None otherwise
        """
        if not equipment_item:
            return None
            
        # Check if current equipment has location
        equipment_semantics = equipment_item.get("metadata", {}).get("semantics", {})
        location_name = equipment_semantics.get("config", {}).get("hasLocation")
        
        if location_name:
            # Find location item in the equipment's parents
            location_item = self._find_parent_by_name(
                equipment_item.get("parents", []), location_name
            )
            if location_item:
                return self._build_location_hierarchy(location_item)
        
        # Check if current equipment has parent equipment (isPartOf)
        parent_equipment_name = equipment_semantics.get("config", {}).get("isPartOf")
        if parent_equipment_name:
            # Find parent equipment in the equipment's parents
            parent_equipment_item = self._find_parent_by_name(
                equipment_item.get("parents", []), parent_equipment_name
            )
            if parent_equipment_item:
                # Recursively search in parent equipment
                return self._find_equipment_location_recursive(parent_equipment_item, all_parents)
        
        return None

    def _build_equipment_hierarchy(self, equipment_item: dict) -> Equipment:
        """Recursively build Equipment objects with parent relationships using semantic labels."""
        # Extract semantic information
        semantics = equipment_item.get("metadata", {}).get("semantics", {})
        semantics_value = semantics.get("value", "")
        equipment_name = equipment_item.get("name")
        
        # Get equipment type (remove "Equipment_" prefix)
        equipment_type = semantics_value.replace("Equipment_", "") if semantics_value else ""
        equipment_hierarchy = equipment_type.split("_")
        equipment_full = "_".join(equipment_hierarchy)  # Full hierarchy for indexing
        equipment_short_name = equipment_hierarchy[-1]  # Just "Downlight" for LLM
        
        # Check for parent equipment via isPartOf relationship
        parent_equipment = None
        config = semantics.get("config", {})
        parent_equipment_name = config.get("isPartOf")
        
        if parent_equipment_name:
            parent_equipment_item = self._find_parent_by_name(
                equipment_item.get("parents", []), parent_equipment_name
            )
            if parent_equipment_item:
                parent_equipment, _, _ = self._build_equipment_hierarchy(parent_equipment_item)
        
        # Create equipment object
        equipment = Equipment(
            type=equipment_full,  # Use full hierarchy for type
            id=equipment_name,
            label=equipment_item.get("label"),
            parent=parent_equipment,
        )
        
        # Return equipment with both naming schemes
        return equipment, equipment_short_name, equipment_full

    def _build_location_hierarchy(self, location_item: dict) -> Location:
        """Recursively build Location objects with parent relationships using semantic labels."""
        # Extract semantic information
        semantics = location_item.get("metadata", {}).get("semantics", {})
        semantics_value = semantics.get("value", "")

        if not semantics_value.startswith("Location_"):
            return Location(
                name=location_item["name"], label=location_item.get("label")
            )

        # Extract location hierarchy from semantic value: Location_Indoor_Room_LivingRoom
        location_hierarchy = semantics_value.replace("Location_", "").split("_")
        location_full = "_".join(location_hierarchy)  # Keep full hierarchy for indexing
        location_name = location_hierarchy[-1]  # Just "LivingRoom" for LLM

        # Create the current location
        current_location = Location(
            name=location_full,  # Use full semantic hierarchy as name
            label=location_item.get("label")
        )

        # Check if this location has a parent (isPartOf in semantics)
        location_config = semantics.get("config", {})
        parent_name = location_config.get("isPartOf")

        if parent_name:
            # Find the parent location item in location's own parents
            parent_item = self._find_parent_by_name(
                location_item.get("parents", []), parent_name
            )
            if parent_item:
                # Recursively build parent hierarchy
                parent_location, _, _ = self._build_location_hierarchy(parent_item)
                current_location.parent = parent_location

        # Return location with both naming schemes
        return current_location, location_name, location_full

    def start_sse_listener(
        self,
        callback: Callable[[str, State], None] = None,
        item_names: List[str] = None,
    ):
        """Start Server-Sent Events listener for real-time state updates.

        Args:
            callback: Function to call when state updates occur
            item_names: List of item names to monitor
        """
        if self._sse_running:
            logger.warning("SSE listener is already running")
            return

        self._sse_running = True
        self._sse_stop_event.clear()
        self._item_names = item_names  # Store item names for channel configuration
        self._sse_callback = callback

        # Start SSE worker thread
        self._sse_thread = threading.Thread(target=self._sse_worker, daemon=True)
        self._sse_thread.start()
        logger.info("SSE listener started")

    def _sse_worker(self):
        """Worker function for SSE listening"""
        channel_id = None
        items_posted = False

        while not self._sse_stop_event.is_set():
            try:
                logger.info("Connecting to SSE stream...")
                response = self.session.get(
                    f"{self.base_url}/rest/events/states",
                    headers={"accept": "*/*"},
                    stream=True,
                    timeout=30,
                )
                response.raise_for_status()

                logger.info("Connected to SSE stream, waiting for channel ID...")

                for event in sseclient.SSEClient(response).events():
                    if self._sse_stop_event.is_set():
                        break

                    # Handle SSE event format
                    if hasattr(event, "event") and hasattr(event, "data"):
                        # SSE event with event type and data
                        event_type = event.event
                        event_data = event.data

                        if not channel_id and event_type == "ready":
                            channel_id = event_data
                            self._channel_id = channel_id
                            logger.info("Got SSE channel ID: %s", channel_id)
                            self.update_sse_items(self._item_names)
                            continue

                        if event_data and event_type == "message":
                            try:
                                # Try to parse event data as JSON
                                parsed_data = json.loads(event_data)
                                for item_name, item_data in parsed_data.items():
                                    state_obj = State(
                                        value=item_data.get("state"),
                                        display_state=item_data.get("displayState"),
                                        state_type=item_data.get("type"),
                                        numeric_state=item_data.get("numericState"),
                                        unit=item_data.get("unit"),
                                    )
                                    self._sse_callback(item_name, state_obj)
                            except Exception as e:
                                logger.error("Error processing event data: %s", e)
            except Exception as e:
                logger.error("SSE connection error: %s", e)
                if not self._sse_stop_event.is_set():
                    logger.info("Reconnecting in 5 seconds...")
                    time.sleep(5)
                else:
                    break

    def update_sse_items(self, item_names: List[str]):
        """Update items for existing SSE channel

        Args:
            item_names: List of item names to filter for

        Returns:
            bool: True if update was successful, False otherwise
        """
        if not hasattr(self, "_channel_id") or not self._channel_id:
            logger.warning("No active SSE channel - call start_sse_listener first")
            return False

        logger.info("Updating SSE channel with %s items", len(item_names))
        channel_url = f"{self.base_url}/rest/events/states/{self._channel_id}"
        items_json = json.dumps(item_names)

        try:
            post_response = self.session.post(
                channel_url,
                data=items_json,
                headers={"Content-Type": "application/json"},
            )
            post_response.raise_for_status()
            logger.info(
                "Successfully updated SSE channel with %s items", len(item_names)
            )
            self._item_names = item_names  # Update stored item names
            return True
        except Exception as e:
            logger.error("Failed to update SSE channel: %s", e)
            return False

    def stop_sse_listener(self):
        """Stop the SSE listener"""
        if not self._sse_running:
            logger.info("SSE listener is not running")
            return

        self._sse_running = False
        self._sse_stop_event.set()

        if self._sse_thread and self._sse_thread.is_alive():
            self._sse_thread.join(timeout=5)

        logger.info("SSE listener stopped")

    def send_command(self, item_name: str, command: str) -> dict:
        """Send a command to an OpenHAB item

        Args:
            item_name: Name of the item to command
            command: Command to send

        Returns:
            dict: Result with success status and optional error details
        """
        try:
            url = f"{self.base_url}/rest/items/{item_name}"
            response = self.session.post(
                url, data=command, headers={"Content-Type": "text/plain"}
            )
            response.raise_for_status()
            logger.info(
                "Successfully sent command '%s' to item '%s'", command, item_name
            )
            return {"success": True}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.reason}"
            logger.error("Failed to send command to item '%s': %s", item_name, error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            logger.error("Failed to send command to item '%s': %s", item_name, e)
            return {
                "success": False,
                "error": str(e)
            }

    def post_update(self, item_name: str, state: str) -> dict:
        """Post a state update to an OpenHAB item

        Args:
            item_name: Name of the item to update
            state: New state value

        Returns:
            dict: Result with success status and optional error details
        """
        try:
            url = f"{self.base_url}/rest/items/{item_name}/state"
            response = self.session.post(
                url, data=state, headers={"Content-Type": "text/plain"}
            )
            response.raise_for_status()
            logger.info(
                "Successfully updated state '%s' for item '%s'", state, item_name
            )
            return {"success": True}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.reason}"
            logger.error("Failed to update state for item '%s': %s", item_name, error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            logger.error("Failed to update state for item '%s': %s", item_name, e)
            return {
                "success": False,
                "error": str(e)
            }
