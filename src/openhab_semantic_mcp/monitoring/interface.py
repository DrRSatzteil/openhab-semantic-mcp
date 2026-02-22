import abc
from datetime import datetime
from typing import Optional

from .models import MonitoringTask, TaskUpdate, MonitoringIntent


class MonitoringStorageInterface(abc.ABC):
    """Interface for monitoring storage."""

    @abc.abstractmethod
    def create_task(
        self,
        mode,
        filters=None,
        refinement=None,
        intent: MonitoringIntent = None,
        start_time=None,
        end_time=None,
    ) -> MonitoringTask:
        """Create a new monitoring task with backend-generated ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_task(self, task_id: str) -> None:
        """Delete a monitoring task by ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """Get a monitoring task by ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def update_task(self, task_id: str, updates: TaskUpdate) -> None:
        """Update a monitoring task."""
        raise NotImplementedError

    @abc.abstractmethod
    def cleanup_tasks(self, status: str, before_timestamp: datetime) -> tuple[int, int]:
        """Remove tasks with given status that were already in this state before timestamp.

        Returns count of cleaned tasks.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_all_tasks(self) -> dict[str, MonitoringTask]:
        """Get all monitoring tasks."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_active_tasks(self) -> dict[str, MonitoringTask]:
        """Get all tasks with status 'active'."""
        raise NotImplementedError
