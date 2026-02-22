"""In-memory monitoring storage backend for testing and development."""

import uuid
from datetime import datetime
from typing import Dict, Optional

from ..interface import MonitoringStorageInterface
from ..models import (
    MonitoringTask,
    TaskUpdate,
    MonitoringIntent,
    new_monitoring_task,
)


class MemoryMonitoringStorage(MonitoringStorageInterface):
    """In-memory storage implementation for monitoring tasks.

    This backend stores monitoring tasks in memory only.
    Data is lost when the application restarts.
    Useful for testing and development.
    """

    def __init__(self, config: dict):
        self.tasks: Dict[str, MonitoringTask] = {}
        self.config = config
        self.timezone = config.get("timezone", "UTC")

    def create_task(
        self,
        mode,
        filters=None,
        refinement=None,
        intent: MonitoringIntent = None,
        start_time=None,
        end_time=None,
    ) -> MonitoringTask:
        """Create a new monitoring task with generated ID."""
        # Create task with intent included directly
        task = new_monitoring_task(
            mode=mode,
            filters=filters,
            refinement=refinement,
            intent=intent,
            start_time=start_time,
            end_time=end_time,
        )

        # Generate unique task ID in single operation
        task = task.model_copy(update={"task_id": str(uuid.uuid4())})

        # Add to storage
        self.tasks[task.task_id] = task
        return task

    def delete_task(self, task_id: str) -> None:
        """Delete a task by ID. Silently ignores if task doesn't exist."""
        self.tasks.pop(task_id, None)

    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """Get a monitoring task by ID."""
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, updates: TaskUpdate) -> None:
        """Update a monitoring task."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        current_task = self.tasks[task_id]
        # Apply updates to the task
        updated_task = current_task.apply_updates(updates)
        self.tasks[task_id] = updated_task

    def get_all_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all monitoring tasks."""
        return dict(self.tasks.items())

    def get_active_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all tasks with status 'active'."""
        return {
            task_id: task
            for task_id, task in self.tasks.items()
            if task.status == "active"
        }

    def cleanup_tasks(self, status: str, before_timestamp: datetime) -> tuple[int, int]:
        """Remove tasks with given status before timestamp.

        Args:
            status: Task status to filter by
            before_timestamp: Delete tasks with last_state_transition before this time

        Returns:
            Tuple of (successful_cleanups, failed_cleanups).
        """
        original_count = len(self.tasks)
        self.tasks = {
            task_id: task
            for task_id, task in self.tasks.items()
            if not (
                task.status == status
                and task.last_state_transition
                and task.last_state_transition < before_timestamp
            )
        }
        deleted_count = original_count - len(self.tasks)
        return deleted_count, 0

    def clear_all(self) -> int:
        """Clear all tasks (useful for testing)."""
        count = len(self.tasks)
        self.tasks.clear()
        return count
