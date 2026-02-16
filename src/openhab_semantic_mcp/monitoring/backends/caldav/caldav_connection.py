"""CalDAV connection management for monitoring backend."""

import logging
from typing import Optional

import requests
from caldav import DAVClient
from caldav.lib.error import DAVError

from .caldav_config import CalDAVConfig
from .exceptions import CalDAVConnectionError, CalDAVCalendarError

logger = logging.getLogger(__name__)


class CalDAVConnection:
    """Manages CalDAV server connection and calendar access."""

    def __init__(self, config: CalDAVConfig):
        self.config = config
        self.dav_client: Optional[DAVClient] = None
        self.calendar = None

    def connect(self) -> bool:
        """Establish connection to CalDAV server and get calendar."""
        try:
            self.dav_client = DAVClient(
                url=self.config.url,
                username=self.config.username,
                password=self.config.password,
            )

            # Test connection
            principal = self.dav_client.principal()
            calendars = principal.calendars()

            # Find or create monitoring calendar
            self.calendar = self._get_or_create_calendar(calendars)

            logger.info("Connected to CalDAV calendar: %s", self.calendar.name)
            return True

        except (DAVError, requests.RequestException) as e:
            logger.error("Failed to connect to CalDAV server: %s", e)
            raise CalDAVConnectionError(self.config.url, str(e)) from e

    def _get_or_create_calendar(self, calendars):
        """Get existing calendar or create new one."""
        # Try to find existing calendar by name
        for cal in calendars:
            if cal.name == self.config.calendar_name:
                logger.info("Found existing calendar: %s", self.config.calendar_name)
                return cal

        # Create new calendar if not found
        try:
            principal = self.dav_client.principal()
            new_calendar = principal.make_calendar(
                name=self.config.calendar_name,
                cal_id=self.config.calendar_name.lower().replace(" ", "_"),
            )
            logger.info("Created new calendar: %s", self.config.calendar_name)
            return new_calendar
        except (DAVError, requests.RequestException) as e:
            logger.error(
                "Failed to create calendar %s: %s", self.config.calendar_name, e
            )
            raise CalDAVCalendarError(
                self.config.calendar_name, "creation", str(e)
            ) from e

    def is_connected(self) -> bool:
        """Check if connection is established."""
        return self.dav_client is not None and self.calendar is not None

    def get_calendar(self):
        """Get the calendar object."""
        return self.calendar

    def test_connection(self) -> bool:
        """Test the connection by fetching calendar properties."""
        if not self.is_connected():
            return False

        try:
            # Try to get calendar properties
            props = self.calendar.get_properties(
                ["displayname", "calendar-description"]
            )
            logger.debug("Calendar properties: %s", props)
            return True
        except (DAVError, requests.RequestException) as e:
            logger.error("Connection test failed: %s", e)
            return False
