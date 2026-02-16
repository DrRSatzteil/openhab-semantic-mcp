"""Tests for monitoring storage backends."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import tempfile

import pytest

from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    TaskStatus,
    TaskUpdate,
    set_default_timezone,
)
from openhab_semantic_mcp.monitoring.backends.memory import MemoryMonitoringStorage
from openhab_semantic_mcp.monitoring.backends.file import FileMonitoringStorage


def create_backend_config(**kwargs):
    """Helper to create backend config dict."""
    defaults = {"timezone": "UTC"}
    defaults.update(kwargs)
    return defaults


class TestMemoryStorage:
    """Test memory-based monitoring storage."""

    def setup_method(self):
        """Set up test storage."""
        set_default_timezone("UTC")
        config = create_backend_config()
        self.storage = MemoryMonitoringStorage(config)

    def test_create_task(self):
        """Test creating a task in memory storage."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.task_id is not None
        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.status == TaskStatus.ACTIVE

    def test_get_task(self):
        """Test retrieving a task by ID."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        created_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT, end_time=end_time
        )

        retrieved_task = self.storage.get_task(created_task.task_id)

        assert retrieved_task is not None
        assert retrieved_task.task_id == created_task.task_id
        assert retrieved_task.mode == created_task.mode

    def test_get_nonexistent_task(self):
        """Test retrieving a task that doesn't exist."""
        task = self.storage.get_task("nonexistent-id")
        assert task is None

    def test_get_all_tasks(self):
        """Test retrieving all tasks."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task1 = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT, end_time=end_time
        )
        task2 = self.storage.create_task(
            mode=MonitoringMode.TIME_WINDOW, end_time=end_time
        )

        all_tasks = self.storage.get_all_tasks()

        assert len(all_tasks) == 2
        assert task1.task_id in all_tasks
        assert task2.task_id in all_tasks

    def test_get_active_tasks(self):
        """Test retrieving only active tasks."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        active_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT, end_time=end_time
        )

        # Create a completed task
        completed_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(),
        )

        active_tasks = self.storage.get_active_tasks()

        assert len(active_tasks) == 1
        assert active_task.task_id in active_tasks
        assert completed_task.task_id not in active_tasks

    def test_update_task(self):
        """Test updating a task."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        updates = TaskUpdate(status=TaskStatus.COMPLETED, update_state_transition=True)
        self.storage.update_task(task.task_id, updates)

        updated_task = self.storage.get_task(task.task_id)
        assert updated_task.status == TaskStatus.COMPLETED

    def test_update_nonexistent_task(self):
        """Test updating a task that doesn't exist."""
        updates = TaskUpdate(status=TaskStatus.COMPLETED)

        with pytest.raises(ValueError, match="not found"):
            self.storage.update_task("nonexistent-id", updates)

    def test_delete_task(self):
        """Test deleting a task."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        self.storage.delete_task(task.task_id)

        retrieved_task = self.storage.get_task(task.task_id)
        assert retrieved_task is None

    def test_delete_nonexistent_task(self):
        """Test that deleting nonexistent task doesn't raise error."""
        # Should not raise an error
        self.storage.delete_task("nonexistent-id")

    def test_cleanup_completed_tasks(self):
        """Test cleaning up old completed tasks."""
        # Create a completed task from 10 days ago
        old_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(days=10)).isoformat(),
        )

        # Update last_state_transition to simulate old task
        old_transition_time = datetime.now(ZoneInfo("UTC")) - timedelta(days=10)
        self.storage.update_task(
            old_task.task_id,
            TaskUpdate(
                last_state_transition=old_transition_time,
                update_state_transition=False,  # Don't auto-update to now
            ),
        )

        # Create a recent completed task
        recent_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(),
        )

        # Cleanup tasks older than 7 days
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=7)
        deleted, failed = self.storage.cleanup_tasks(
            status=TaskStatus.COMPLETED.value, before_timestamp=cutoff
        )

        assert deleted == 1
        assert failed == 0

        # Old task should be gone
        assert self.storage.get_task(old_task.task_id) is None

        # Recent task should still exist
        assert self.storage.get_task(recent_task.task_id) is not None

    def test_task_isolation(self):
        """Test that tasks in different storage instances are isolated."""
        storage1 = MemoryMonitoringStorage(create_backend_config())
        storage2 = MemoryMonitoringStorage(create_backend_config())

        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task1 = storage1.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        # Task should not exist in storage2
        assert storage2.get_task(task1.task_id) is None


class TestFileStorage:
    """Test file-based monitoring storage."""

    def setup_method(self):
        """Set up test storage with temporary file."""
        set_default_timezone("UTC")
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        )
        self.temp_file.close()

        self.storage = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

    def teardown_method(self):
        """Clean up temporary file."""
        Path(self.temp_file.name).unlink(missing_ok=True)

    def test_create_task_persists_to_file(self):
        """Test that created tasks are persisted to file."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        # Create new storage instance with same file
        storage2 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

        # Task should be loaded from file
        retrieved_task = storage2.get_task(task.task_id)
        assert retrieved_task is not None
        assert retrieved_task.task_id == task.task_id

    def test_update_task_persists_to_file(self):
        """Test that task updates are persisted to file."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        updates = TaskUpdate(status=TaskStatus.COMPLETED, update_state_transition=True)
        self.storage.update_task(task.task_id, updates)

        # Create new storage instance
        storage2 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

        # Updated status should be persisted
        retrieved_task = storage2.get_task(task.task_id)
        assert retrieved_task.status == TaskStatus.COMPLETED

    def test_delete_task_removes_from_file(self):
        """Test that deleted tasks are removed from file."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        self.storage.delete_task(task.task_id)

        # Create new storage instance
        storage2 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

        # Task should not exist
        assert storage2.get_task(task.task_id) is None

    def test_file_creation_on_first_write(self):
        """Test that file is created on first write."""
        nonexistent_file = Path(tempfile.gettempdir()) / "test_monitoring_new.json"
        nonexistent_file.unlink(missing_ok=True)

        try:
            storage = FileMonitoringStorage(
                create_backend_config(file_path=str(nonexistent_file))
            )

            end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
            storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

            # File should now exist
            assert nonexistent_file.exists()

        finally:
            nonexistent_file.unlink(missing_ok=True)

    def test_concurrent_file_access(self):
        """Test that multiple storage instances can access the same file."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        storage1 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )
        storage2 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

        # Create task with storage1
        task1 = storage1.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        # Storage2 should see it after reload
        storage2.tasks = storage2._load_tasks()
        assert storage2.get_task(task1.task_id) is not None

    def test_cleanup_persists_to_file(self):
        """Test that cleanup operations persist to file."""
        # Create old completed task
        old_task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(days=10)).isoformat(),
        )

        # Update last_state_transition to simulate old task
        old_transition_time = datetime.now(ZoneInfo("UTC")) - timedelta(days=10)
        self.storage.update_task(
            old_task.task_id,
            TaskUpdate(
                last_state_transition=old_transition_time, update_state_transition=False
            ),
        )

        # Cleanup
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=7)
        self.storage.cleanup_tasks(
            status=TaskStatus.COMPLETED.value, before_timestamp=cutoff
        )

        # Create new storage instance
        storage2 = FileMonitoringStorage(
            create_backend_config(file_path=self.temp_file.name)
        )

        # Task should not exist
        assert storage2.get_task(old_task.task_id) is None


class TestStorageTimezoneHandling:
    """Test timezone handling across storage backends."""

    def test_memory_storage_timezone_consistency(self):
        """Test that memory storage maintains timezone consistency."""
        set_default_timezone("America/New_York")

        storage = MemoryMonitoringStorage(
            create_backend_config(timezone="America/New_York")
        )

        end_time = (
            datetime.now(ZoneInfo("America/New_York")) + timedelta(hours=1)
        ).isoformat()
        task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.time_window.start_time.tzinfo.key == "America/New_York"
        assert task.time_window.end_time.tzinfo.key == "America/New_York"

    def test_file_storage_timezone_persistence(self):
        """Test that file storage persists timezone information."""
        set_default_timezone("Europe/Berlin")

        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
        temp_file.close()

        try:
            storage = FileMonitoringStorage(
                create_backend_config(
                    file_path=temp_file.name, timezone="Europe/Berlin"
                )
            )

            end_time = (
                datetime.now(ZoneInfo("Europe/Berlin")) + timedelta(hours=1)
            ).isoformat()
            task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

            # Create new storage instance
            storage2 = FileMonitoringStorage(
                create_backend_config(
                    file_path=temp_file.name, timezone="Europe/Berlin"
                )
            )

            retrieved_task = storage2.get_task(task.task_id)
            assert retrieved_task.time_window.start_time.tzinfo.key == "Europe/Berlin"

        finally:
            Path(temp_file.name).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
