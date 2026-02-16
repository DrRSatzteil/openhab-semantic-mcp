"""
CalDAV calendar synchronizer for monitoring tasks.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo

from .caldav_connection import CalDAVConnection
from .calendar_event_mapper import CalendarEventMapper
from ...models import MonitoringTask
from .exceptions import CalDAVConnectionError, CalDAVCalendarError

logger = logging.getLogger(__name__)


class CalendarSynchronizer:
    """Simplified CalDAV calendar synchronizer."""

    def __init__(
        self,
        connection: CalDAVConnection,
        storage=None,
        sync_interval: int = 0,
        timezone: str = "UTC",
    ):
        self.connection = connection
        self.storage = storage
        self.sync_interval = sync_interval
        self.timezone = timezone
        self._stop_event = threading.Event()
        self._thread = None

    # ----------------------------
    # Background worker
    # ----------------------------
    def start_sync_worker(self):
        """Start the background sync worker thread."""
        if self.sync_interval <= 0:
            return

        self._thread = threading.Thread(
            target=self._sync_worker, name="CalDAV-Sync", daemon=True
        )
        self._thread.start()
        logger.info(
            "Started CalDAV sync worker with interval %s seconds", self.sync_interval
        )

    def stop_sync_worker(self):
        """Stop the background sync worker thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Stopped CalDAV sync worker")

    def _sync_worker(self):
        """Background worker that syncs calendar events to monitoring tasks."""
        while not self._stop_event.wait(self.sync_interval):
            try:
                self.sync_from_calendar()
            except CalDAVCalendarError as e:
                logger.error("Background sync failed: %s", e)

    # ----------------------------
    # Sync logic
    # ----------------------------
    def sync_from_calendar(self) -> Dict[str, MonitoringTask]:
        """
        Sync calendar events to monitoring tasks.

        Returns:
            Dict[str, MonitoringTask]: Dictionary of synced tasks by task_id

        Raises:
            CalDAVConnectionError: If not connected to CalDAV server
            CalDAVCalendarError: If calendar synchronization fails
        """
        if not self.connection.is_connected():
            raise CalDAVConnectionError(self.connection.config.url, "Not connected")

        try:
            calendar = self.connection.get_calendar()
            synced_tasks = {}

            local_task_ids = set(self.storage.get_all_tasks().keys())

            # Use date_search with wide range - calendar.events() may not
            # return past events on some CalDAV servers (e.g. Nextcloud)
            now = datetime.now(timezone.utc)
            search_start = now - timedelta(days=365)
            search_end = now + timedelta(days=365)
            events = calendar.date_search(start=search_start, end=search_end)
            logger.debug("Found %d calendar events", len(events))

            for event in events:
                # date_search results may have event.id=None, get UID from component
                component = getattr(event, "component", None)
                event_id = (
                    str(component.get("uid"))
                    if component and component.get("uid")
                    else None
                )
                if not event_id:
                    logger.warning("Event missing UID, skipping")
                    continue

                try:
                    task = CalendarEventMapper.parse_event_to_task(event)
                    if task:
                        task.task_id = event_id
                        synced_tasks[task.task_id] = task
                    else:
                        logger.warning(
                            "Event %s skipped (no parseable monitoring data)",
                            event_id,
                        )

                except Exception as e:
                    logger.warning(
                        "Failed to parse event %s: %s: %s",
                        event_id,
                        type(e).__name__,
                        e,
                    )

            calendar_task_ids = set(synced_tasks.keys())
            removed_task_ids = local_task_ids - calendar_task_ids
            for task_id in removed_task_ids:
                try:
                    self.storage.delete_task(task_id)
                    logger.info("Deleted task %s", task_id)
                except CalDAVCalendarError:
                    # Delete will throw an exception because the task no longer exists in the calendar
                    pass

            logger.info(
                "Synced %d tasks from calendar and deleted %d no longer existing tasks",
                len(synced_tasks),
                len(removed_task_ids),
            )
            return synced_tasks

        except Exception as e:
            logger.error("Calendar sync failed: %s", e)
            calendar_name = calendar.get_display_name() or "Unknown"
            raise CalDAVCalendarError(calendar_name, "sync", str(e)) from e

    # ----------------------------
    # Calendar event CRUD
    # ----------------------------
    def create_event(self, task: MonitoringTask) -> MonitoringTask:
        """
        Create a calendar event for the given monitoring task.

        Args:
            task: Monitoring task to create event for

        Returns:
            MonitoringTask with task_id set

        Raises:
            CalDAVConnectionError: If not connected to CalDAV server
            CalDAVCalendarError: If event creation fails
        """
        if not self.connection.is_connected():
            logger.error("Cannot create event: CalDAV not connected")
            raise CalDAVConnectionError(
                self.connection.config.url, "Not connected to CalDAV server"
            )

        try:
            calendar = self.connection.get_calendar()
            title = CalendarEventMapper.generate_calendar_title(task)

            # Create a copy of task data without task_id to avoid confusion in sync
            description = task.model_dump_json(exclude={"task_id"})

            # Create calendar event - this will generate the real UID
            event = calendar.save_event(
                dtstart=task.time_window.start_time,
                dtend=task.time_window.end_time,
                summary=title,
                description=description,
            )

            task.task_id = str(event.id)

            logger.info("Created calendar event for task %s", task.task_id)
            return task

        except Exception as e:
            logger.error(
                "Failed to create calendar event for task %s: %s", task.task_id, e
            )
            raise CalDAVCalendarError(
                self.connection.config.calendar_name, "create", str(e)
            ) from e

    def update_event(self, task: MonitoringTask) -> MonitoringTask:
        """
        Update a calendar event for the given monitoring task.

        Args:
            task: Monitoring task to update event for

        Returns:
            MonitoringTask with updated event

        Raises:
            CalDAVConnectionError: If not connected to CalDAV server
            CalDAVCalendarError: If event update fails
        """
        if not self.connection.is_connected():
            logger.error("Cannot update event: CalDAV not connected")
            raise CalDAVConnectionError(
                self.connection.config.url, "Not connected to CalDAV server"
            )

        try:
            calendar = self.connection.get_calendar()
            event = calendar.event_by_uid(uid=task.task_id)
            if not event:
                logger.warning(
                    "No event found with UID %s for task %s", task.task_id, task.task_id
                )
                return None

            vobject = event.vobject_instance
            vevent = vobject.vevent
            vevent.summary.value = CalendarEventMapper.generate_calendar_title(task)

            vevent.description.value = task.model_dump_json(exclude={"task_id"})

            # Use configured timezone
            tz = ZoneInfo(self.timezone)

            # Datetimes auf server-Zeitzone konvertieren
            vevent.dtstart.value = task.time_window.start_time.astimezone(tz)
            vevent.dtend.value = task.time_window.end_time.astimezone(tz)

            event.save()
            logger.info("Updated calendar event for task %s", task.task_id)
            return task

        except Exception as e:
            logger.error(
                "Failed to update calendar event for task %s: %s", task.task_id, e
            )
            raise CalDAVCalendarError(
                self.connection.config.calendar_name, "update", str(e)
            ) from e

    def delete_event(self, task: MonitoringTask) -> bool:
        """
        Delete a calendar event for the given monitoring task.

        Args:
            task: Monitoring task to delete event for

        Returns:
            MonitoringTask with deleted event

        Raises:
            CalDAVConnectionError: If not connected to CalDAV server
            CalDAVCalendarError: If event deletion fails
        """
        if not self.connection.is_connected():
            logger.error("Cannot delete event: CalDAV not connected")
            raise CalDAVConnectionError(
                self.connection.config.url, "Not connected to CalDAV server"
            )

        try:
            calendar = self.connection.get_calendar()
            event = calendar.event_by_uid(uid=task.task_id)
            if event:
                event.delete()
                logger.info("Deleted calendar event for task %s", task.task_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to delete calendar event for task %s: %s", task.task_id, e
            )
            raise CalDAVCalendarError(
                self.connection.config.calendar_name, "delete", str(e)
            ) from e
