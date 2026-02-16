"""
File-based monitoring storage backend.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from pydantic import ValidationError
from ..interface import MonitoringStorageInterface
from ..models import (
    MonitoringTask,
    TaskUpdate,
    get_timezone_aware_datetime,
    new_monitoring_task,
)

logger = logging.getLogger(__name__)


class FileMonitoringStorage(MonitoringStorageInterface):
    """File-based monitoring storage backend."""

    def __init__(self, config: dict):
        self.file_path = config.get("file_path", "monitoring_tasks.json")
        self.timezone = config.get("timezone", "UTC")
        self.tasks = self._load_tasks()

    def _load_tasks(self) -> Dict[str, MonitoringTask]:
        """Load tasks from file and convert to MonitoringTask objects."""
        try:
            if Path(self.file_path).exists():
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tasks = {}
                    for task_id, task_data in data.items():
                        try:
                            # Convert dict to MonitoringTask
                            tasks[task_id] = MonitoringTask(**task_data)
                        except ValidationError as e:
                            logger.warning("Failed to load task %s: %s", task_id, e)
                    return tasks
        except (json.JSONDecodeError, OSError, IOError) as e:
            logger.error("Failed to load monitoring tasks: %s", e)
        return {}

    def _save_tasks(self):
        """Save tasks to file, converting MonitoringTask objects to dicts."""
        try:
            # Convert MonitoringTask objects to dicts for JSON serialization
            data = {task_id: task.model_dump() for task_id, task in self.tasks.items()}
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except (TypeError, OSError, IOError) as e:
            logger.error("Failed to save monitoring tasks: %s", e)

    def create_task(
        self,
        mode,
        filters=None,
        refinement=None,
        start_time=None,
        end_time=None,
    ) -> MonitoringTask:
        """Create a new monitoring task with generated ID."""
        task = new_monitoring_task(
            mode=mode,
            filters=filters,
            refinement=refinement,
            start_time=start_time,
            end_time=end_time,
        )

        # Generate unique task ID
        task_id = str(uuid.uuid4())
        task = task.model_copy(update={"task_id": task_id})

        self.tasks[task_id] = task
        self._save_tasks()
        return task

    def delete_task(self, task_id: str) -> None:
        if task_id not in self.tasks:
            logger.warning("Task %s not found for deletion", task_id)
            return
        del self.tasks[task_id]
        self._save_tasks()

    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """Get a monitoring task by ID."""
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, updates: TaskUpdate) -> None:
        """Update a monitoring task."""
        current_task = self.tasks.get(task_id)
        if not current_task:
            raise ValueError(f"Task {task_id} not found")

        # Apply updates using model's apply_updates method
        updated_task = current_task.apply_updates(updates)
        self.tasks[task_id] = updated_task
        self._save_tasks()

    def cleanup_tasks(self, status: str, before_timestamp: datetime) -> tuple[int, int]:
        """Remove tasks with given status that existed before timestamp.

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

        if deleted_count > 0:
            self._save_tasks()

        return deleted_count, 0

    def get_all_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all monitoring tasks."""
        return dict(self.tasks)

    def get_active_tasks(self) -> Dict[str, MonitoringTask]:
        """Get all tasks with status 'active'."""
        return {
            task_id: task
            for task_id, task in self.tasks.items()
            if task.status == "active"
        }
