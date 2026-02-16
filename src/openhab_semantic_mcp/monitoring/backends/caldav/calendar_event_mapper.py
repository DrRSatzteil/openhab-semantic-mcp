"""Calendar event mapping between MonitoringTask and calendar events."""

import json
import logging
import re

from .exceptions import CalDAVEventError
from ...models import MonitoringTask

logger = logging.getLogger(__name__)


class CalendarEventMapper:
    """Maps between MonitoringTask objects and calendar events."""

    @staticmethod
    def parse_event_to_task(event) -> MonitoringTask:
        """Parse calendar event to monitoring task"""
        try:
            caldav_event = event
            vevent = caldav_event.vobject_instance.vevent

            description = (
                getattr(vevent, "description", None) and vevent.description.value
            )

            if description:
                try:
                    task_data = json.loads(description)

                    task_data.update(
                        {
                            "task_id": str(caldav_event.id),
                            "time_window": {
                                "start_time": getattr(vevent, "dtstart", None)
                                and vevent.dtstart.value,
                                "end_time": getattr(vevent, "dtend", None)
                                and vevent.dtend.value,
                            },
                        }
                    )

                    return MonitoringTask(**task_data)

                except json.JSONDecodeError:
                    logger.debug(
                        "Could not parse description as JSON: %s",
                        description,
                    )

        except Exception as e:
            logger.error("Failed to parse event to task: %s", e)
            raise CalDAVEventError(caldav_event.id, "parse", str(e)) from e

    @staticmethod
    def clean_semantic_name(name: str) -> str:
        """
        Clean up semantic names using rule-based approach.

        Args:
            name: Semantic name to clean

        Returns:
            Cleaned semantic name
        """
        if not name:
            return ""

        # Rule 1: Use only the last part after the last underscore
        last_part = name.split("_")[-1]

        # Rule 2: Replace CamelCasing with space before capital letters
        cleaned = re.sub(r"(?<!^)(?=[A-Z])", " ", last_part)
        return cleaned.strip()

    @staticmethod
    def format_state_value(state_filter: dict) -> str:
        """
        Format state value for display.

        Args:
            state_filter: State filter dictionary

        Returns:
            Formatted state value string
        """
        if not state_filter:
            return "Any"

        if state_filter.get("kind") == "exact":
            states = state_filter.get("states", [])
            if states:
                return str(",".join(states))
        elif state_filter.get("kind") == "range":
            lower = state_filter.get("lowerBound")
            upper = state_filter.get("upperBound")
            if lower is not None and upper is not None:
                return f"{lower}-{upper}"
            elif lower is not None:
                return f">{lower}"
            elif upper is not None:
                return f"<{upper}"

        return "Unknown"

    @staticmethod
    def generate_calendar_title(task: MonitoringTask) -> str:
        """
        Generate user-friendly calendar title from task filters.

        Args:
            task: Monitoring task to generate title for

        Returns:
            User-friendly calendar title
        """

        # Extract filter components
        location = task.filters.get("location")
        equipment = task.filters.get("equipment")
        point = task.filters.get("point")
        property_name = task.filters.get("property")
        state_filter = task.filters.get("state")

        # Build title parts
        parts = []

        if location:
            location_name = CalendarEventMapper.clean_semantic_name(location)
            parts.append(f"📍 {location_name}")

        if equipment:
            equipment_name = CalendarEventMapper.clean_semantic_name(equipment)
            parts.append(f"🔧 {equipment_name}")

        if point:
            point_name = CalendarEventMapper.clean_semantic_name(point)
            parts.append(f"📊 {point_name}")

        if property_name:
            property_name_clean = CalendarEventMapper.clean_semantic_name(property_name)
            parts.append(f"🏷️ {property_name_clean}")

        if state_filter:
            state_value = CalendarEventMapper.format_state_value(state_filter)
            parts.append(f"🎯 {state_value}")

        # Combine parts
        if parts:
            return " | ".join(parts)
        else:
            return f"Monitor Task {task.task_id[:8]}..."
