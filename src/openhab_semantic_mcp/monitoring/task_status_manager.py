"""Task status management for monitoring operations."""

import logging

from .models import (
    MonitoringTask,
    TaskStatus,
    TaskUpdate,
)

logger = logging.getLogger(__name__)


class TaskStatusManager:
    """Manages task status updates and transitions."""

    def __init__(self, monitoring_store):
        self.monitoring_store = monitoring_store

    def update_task_status(self, task_id: str, status: TaskStatus):
        """Update task status in storage."""
        try:
            task_update = TaskUpdate(status=status, update_state_transition=True)
            self.monitoring_store.update_task(task_id, task_update)
        except Exception as e:
            logger.error("Error updating task status: %s", e)

    def process_task_time_based_transition(self, task: MonitoringTask, current_time):
        """Process task status transition based on time window."""
        if task.status in [
            TaskStatus.CANCELLED.value,
            TaskStatus.ERROR.value,
            TaskStatus.COMPLETED.value,
        ]:
            return

        # Update status based on current time
        if current_time < task.time_window.start_time:
            if task.status != TaskStatus.PENDING.value:
                self.update_task_status(task.task_id, TaskStatus.PENDING)
        elif current_time > task.time_window.end_time:
            if task.status != TaskStatus.COMPLETED.value:
                self.update_task_status(task.task_id, TaskStatus.COMPLETED)
        else:
            if task.status != TaskStatus.ACTIVE.value:
                self.update_task_status(task.task_id, TaskStatus.ACTIVE)
