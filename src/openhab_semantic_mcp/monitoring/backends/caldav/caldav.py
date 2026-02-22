"""
CalDAV monitoring storage backend.
"""

import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from ...interface import MonitoringStorageInterface
from ...models import (
    MonitoringTask,
    TaskStatus,
    TaskUpdate,
    new_monitoring_task,
    MonitoringMode,
    MonitoringIntent,
)
from .caldav_config import CalDAVConfig
from .caldav_connection import CalDAVConnection
from .calendar_synchronizer import CalendarSynchronizer
from .exceptions import CalDAVConnectionError, CalDAVCalendarError

logger = logging.getLogger(__name__)


class CalDAVMonitoringStorage(MonitoringStorageInterface):
    """CalDAV monitoring storage implementation."""

    def __init__(self, config: dict):
        # Initialize configuration
        self.config = CalDAVConfig.from_dict(config)
        self.config.validate()

        # Store timezone for consistent datetime handling (injected by factory)
        self.timezone = config.get("timezone")
        if not self.timezone:
            raise ValueError("Timezone is required in backend configuration")

        # Initialize components
        self.connection = CalDAVConnection(self.config)
        self.synchronizer = CalendarSynchronizer(
            self.connection,
            storage=self,
            sync_interval=self.config.sync_interval,
            timezone=self.timezone,
        )

        # Initialize cache and locks
        self._cache_lock = threading.RLock()
        self._task_cache = {}

        # Connect and initialize
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the storage backend."""
        if not self.connection.connect():
            raise CalDAVConnectionError(
                self.connection.config.url, "Failed to connect to CalDAV server"
            )

        # Initial sync
        self._refresh_cache()

        # Start sync worker if needed
        if self.config.sync_interval > 0:
            self.synchronizer.start_sync_worker()

    def _refresh_cache(self) -> None:
        """Refreshes local cache from calendar."""
        with self._cache_lock:
            synced_tasks = self.synchronizer.sync_from_calendar()
            # Merge with existing cache, preferring calendar data for existing tasks
            self._task_cache.update(synced_tasks)
            logger.info("Refreshed cache with %d tasks", len(self._task_cache))

    def create_task(
        self,
        mode: MonitoringMode,
        filters: Optional[Dict[str, Any]] = None,
        refinement: Optional[Dict[str, Any]] = None,
        intent: MonitoringIntent = None,
        start_time: Optional[str] = None,
        end_time: str = None,
    ) -> MonitoringTask:
        """Create a new monitoring task with CalDAV UID as task ID."""
        new_task = new_monitoring_task(
            mode=mode,
            filters=filters,
            refinement=refinement,
            intent=intent,
            start_time=start_time,
            end_time=end_time,
        )

        # Create calendar event - this will generate real UID
        task_with_id = self.synchronizer.create_event(new_task)
        self._task_cache[task_with_id.task_id] = task_with_id

        return task_with_id

    def delete_task(self, task_id: str) -> None:
        with self._cache_lock:
            if task_id in self._task_cache:
                self.synchronizer.delete_event(self._task_cache[task_id])
                del self._task_cache[task_id]

    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """Get a specific monitoring task."""
        with self._cache_lock:
            return self._task_cache.get(task_id)

    def get_all_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all monitoring tasks from cache."""
        with self._cache_lock:
            return dict(self._task_cache.items())

    def get_active_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all tasks with status 'active' from cache."""
        with self._cache_lock:
            return {
                task_id: task
                for task_id, task in self._task_cache.items()
                if task.status == TaskStatus.ACTIVE.value
            }

    def update_task(self, task_id: str, updates: TaskUpdate) -> None:
        """Update an existing monitoring task."""
        with self._cache_lock:
            # Get current task
            current_task = self._task_cache.get(task_id)
            if not current_task:
                raise ValueError(f"Task {task_id} not found")

            # Apply updates
            updated_task = current_task.apply_updates(updates)

            # Update calendar event
            if not self.synchronizer.update_event(updated_task):
                raise RuntimeError(
                    f"Failed to update calendar event for task {task_id}"
                )

            # Update cache
            self._task_cache[task_id] = updated_task
            logger.info("Updated task %s in calendar and cache", task_id)

    def cleanup_tasks(self, status: str, before_timestamp: datetime) -> tuple[int, int]:
        """Clean up tasks with given status before timestamp."""
        with self._cache_lock:
            tasks_to_delete = []

            # Find tasks to delete
            for task_id, task in self._task_cache.items():
                if (
                    task.status == status
                    and task.last_state_transition
                    and task.last_state_transition < before_timestamp
                ):
                    tasks_to_delete.append(task_id)

            # Delete from calendar and cache
            deleted_count = 0
            failed_count = 0
            for task_id in tasks_to_delete:
                task = self._task_cache[task_id]
                try:
                    if self.synchronizer.delete_event(task):
                        del self._task_cache[task_id]
                        deleted_count += 1
                except CalDAVConnectionError as e:
                    logger.error(
                        "Cannot delete calendar event for task %s: %s (Connection error)",
                        task_id,
                        e,
                    )
                    failed_count += 1
                except CalDAVCalendarError as e:
                    logger.error(
                        "Cannot delete calendar event for task %s: %s (Calendar error)",
                        task_id,
                        e,
                    )
                    failed_count += 1

            logger.info(
                "Cleaned up %d tasks with status '%s' (%d failed)",
                deleted_count,
                status,
                failed_count,
            )
            return deleted_count, failed_count

    def __del__(self):
        """Cleanup when backend is destroyed."""
        try:
            if hasattr(self, "synchronizer"):
                self.synchronizer.stop_sync_worker()
        except (RuntimeError, AttributeError) as e:
            logger.error("Error during cleanup: %s", e)
