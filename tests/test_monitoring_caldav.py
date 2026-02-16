"""Tests for CalDAV monitoring storage backend."""

from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from zoneinfo import ZoneInfo
import uuid

import pytest

from openhab_semantic_mcp.monitoring.backends.caldav.caldav import (
    CalDAVMonitoringStorage,
)
from openhab_semantic_mcp.monitoring.backends.caldav.exceptions import (
    CalDAVConnectionError,
    CalDAVCalendarError,
)
from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    TaskStatus,
    TaskUpdate,
    set_default_timezone,
)


def create_caldav_config(**kwargs):
    """Helper to create CalDAV backend config."""
    defaults = {
        "url": "https://caldav.example.com",
        "username": "test_user",
        "password": "test_password",
        "calendar_name": "OpenHAB Monitoring",
        "sync_interval": 0,  # Disable background sync for tests
        "timezone": "UTC",
    }
    defaults.update(kwargs)
    return defaults


def create_mock_icalendar_component(
    task_id, summary="Test Task", dtstart=None, dtend=None
):
    """Create a mock icalendar component."""
    component = Mock()
    component.uid = task_id

    if dtstart is None:
        dtstart = datetime.now(ZoneInfo("UTC"))
    if dtend is None:
        dtend = dtstart + timedelta(hours=1)

    component.decoded.return_value = {
        "summary": summary,
        "dtstart": dtstart,
        "dtend": dtend,
        "description": "",
    }

    return component


def create_mock_event(task_id, summary="Test Task"):
    """Create a mock CalDAV event."""
    event = Mock()
    event.icalendar_component = create_mock_icalendar_component(task_id, summary)
    event.save = Mock()
    event.delete = Mock()
    return event


@pytest.fixture
def mock_caldav_client():
    """Fixture providing a mocked CalDAV client."""
    with patch(
        "openhab_semantic_mcp.monitoring.backends.caldav.caldav_connection.DAVClient"
    ) as mock_client:
        # Create mock instances
        client_instance = MagicMock()
        principal = MagicMock()
        calendar = MagicMock()

        # Set up the mock chain
        mock_client.return_value = client_instance
        client_instance.principal.return_value = principal
        principal.calendars.return_value = []
        principal.make_calendar.return_value = calendar

        # Calendar properties
        calendar.name = "OpenHAB Monitoring"
        calendar.events.return_value = []
        calendar.save_event = Mock()

        yield {
            "client_class": mock_client,
            "client": client_instance,
            "principal": principal,
            "calendar": calendar,
        }


class TestCalDAVStorageInitialization:
    """Test CalDAV storage initialization and connection."""

    def setup_method(self):
        """Set up test timezone."""
        set_default_timezone("UTC")

    def test_successful_initialization(self, mock_caldav_client):
        """Test successful CalDAV backend initialization."""
        config = create_caldav_config()

        storage = CalDAVMonitoringStorage(config)

        assert storage is not None
        assert storage.config.url == "https://caldav.example.com"
        assert storage.timezone == "UTC"
        assert storage.connection is not None

    def test_initialization_missing_timezone(self, mock_caldav_client):
        """Test that initialization fails without timezone."""
        config = create_caldav_config()
        del config["timezone"]

        with pytest.raises(ValueError, match="Timezone is required"):
            CalDAVMonitoringStorage(config)

    def test_connection_failure(self):
        """Test handling of connection failures."""
        from caldav.lib.error import DAVError

        with patch(
            "openhab_semantic_mcp.monitoring.backends.caldav.caldav_connection.DAVClient"
        ) as mock_client:
            mock_client.side_effect = DAVError("Connection failed")

            config = create_caldav_config()

            with pytest.raises(CalDAVConnectionError):
                CalDAVMonitoringStorage(config)


class TestCalDAVTaskOperations:
    """Test CalDAV task CRUD operations."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")

    @pytest.fixture
    def storage(self, mock_caldav_client):
        """Create a CalDAV storage instance for testing."""
        config = create_caldav_config()

        # Mock the synchronizer to avoid actual calendar operations
        with patch(
            "openhab_semantic_mcp.monitoring.backends.caldav.caldav.CalendarSynchronizer"
        ):
            storage = CalDAVMonitoringStorage(config)
            # Mock the synchronizer methods
            storage.synchronizer.create_event = Mock()
            storage.synchronizer.update_event = Mock(return_value=True)
            storage.synchronizer.delete_event = Mock(return_value=True)
            storage.synchronizer.sync_from_calendar = Mock(return_value={})
            yield storage

    def test_create_task(self, storage):
        """Test creating a task in CalDAV storage."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        # Mock the synchronizer to return a task with ID
        mock_task_id = str(uuid.uuid4())

        def create_event_side_effect(task):
            return task.model_copy(update={"task_id": mock_task_id})

        storage.synchronizer.create_event.side_effect = create_event_side_effect

        task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.task_id == mock_task_id
        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.status == TaskStatus.ACTIVE
        storage.synchronizer.create_event.assert_called_once()

    def test_get_task(self, storage):
        """Test retrieving a task by ID."""
        # Create and add a task to cache
        task_id = str(uuid.uuid4())
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        def create_event_side_effect(task):
            return task.model_copy(update={"task_id": task_id})

        storage.synchronizer.create_event.side_effect = create_event_side_effect

        created_task = storage.create_task(
            mode=MonitoringMode.ONE_SHOT, end_time=end_time
        )

        retrieved_task = storage.get_task(task_id)

        assert retrieved_task is not None
        assert retrieved_task.task_id == task_id

    def test_get_nonexistent_task(self, storage):
        """Test retrieving a task that doesn't exist."""
        task = storage.get_task("nonexistent-id")
        assert task is None

    def test_get_all_tasks(self, storage):
        """Test retrieving all tasks."""
        # Create two tasks
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        created_tasks = []

        for i, task_id in enumerate(task_ids):

            def create_event_side_effect(task, tid=task_id):
                return task.model_copy(update={"task_id": tid})

            storage.synchronizer.create_event.side_effect = create_event_side_effect

            task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)
            created_tasks.append(task)

        all_tasks = storage.get_all_tasks()

        assert len(all_tasks) == 2
        for task_id in task_ids:
            assert task_id in all_tasks

    def test_get_active_tasks(self, storage):
        """Test retrieving only active tasks."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        # Create an active task
        active_id = str(uuid.uuid4())
        storage.synchronizer.create_event.side_effect = lambda t: t.model_copy(
            update={"task_id": active_id}
        )

        active_task = storage.create_task(
            mode=MonitoringMode.ONE_SHOT, end_time=end_time
        )

        # Manually add a completed task to cache
        completed_id = str(uuid.uuid4())
        from openhab_semantic_mcp.monitoring.models import new_monitoring_task

        completed_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(),
        )
        completed_task = completed_task.model_copy(update={"task_id": completed_id})
        storage._task_cache[completed_id] = completed_task

        active_tasks = storage.get_active_tasks()

        assert len(active_tasks) == 1
        assert active_id in active_tasks
        assert completed_id not in active_tasks

    def test_update_task(self, storage):
        """Test updating a task."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task_id = str(uuid.uuid4())

        storage.synchronizer.create_event.side_effect = lambda t: t.model_copy(
            update={"task_id": task_id}
        )

        task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        updates = TaskUpdate(status=TaskStatus.CANCELLED, update_state_transition=True)

        storage.update_task(task_id, updates)

        updated_task = storage.get_task(task_id)
        assert updated_task.status == TaskStatus.CANCELLED
        storage.synchronizer.update_event.assert_called_once()

    def test_update_nonexistent_task(self, storage):
        """Test updating a task that doesn't exist."""
        updates = TaskUpdate(status=TaskStatus.COMPLETED)

        with pytest.raises(ValueError, match="not found"):
            storage.update_task("nonexistent-id", updates)

    def test_update_task_calendar_failure(self, storage):
        """Test handling calendar update failures."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task_id = str(uuid.uuid4())

        storage.synchronizer.create_event.side_effect = lambda t: t.model_copy(
            update={"task_id": task_id}
        )

        task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        # Make calendar update fail
        storage.synchronizer.update_event.return_value = False

        updates = TaskUpdate(status=TaskStatus.CANCELLED)

        with pytest.raises(RuntimeError, match="Failed to update calendar event"):
            storage.update_task(task_id, updates)

    def test_delete_task(self, storage):
        """Test deleting a task."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task_id = str(uuid.uuid4())

        storage.synchronizer.create_event.side_effect = lambda t: t.model_copy(
            update={"task_id": task_id}
        )

        task = storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        storage.delete_task(task_id)

        retrieved_task = storage.get_task(task_id)
        assert retrieved_task is None
        storage.synchronizer.delete_event.assert_called_once()

    def test_delete_nonexistent_task(self, storage):
        """Test that deleting nonexistent task doesn't raise error."""
        # Should not raise an error
        storage.delete_task("nonexistent-id")
        # delete_event should not be called since task doesn't exist
        storage.synchronizer.delete_event.assert_not_called()


class TestCalDAVCleanup:
    """Test CalDAV cleanup operations."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")

    @pytest.fixture
    def storage(self, mock_caldav_client):
        """Create a CalDAV storage instance for testing."""
        config = create_caldav_config()

        with patch(
            "openhab_semantic_mcp.monitoring.backends.caldav.caldav.CalendarSynchronizer"
        ):
            storage = CalDAVMonitoringStorage(config)
            storage.synchronizer.create_event = Mock()
            storage.synchronizer.delete_event = Mock(return_value=True)
            storage.synchronizer.sync_from_calendar = Mock(return_value={})
            yield storage

    def test_cleanup_completed_tasks(self, storage):
        """Test cleaning up old completed tasks."""
        from openhab_semantic_mcp.monitoring.models import new_monitoring_task

        # Create an old completed task
        old_task_id = str(uuid.uuid4())
        old_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(days=10)).isoformat(),
        )
        old_task = old_task.model_copy(
            update={
                "task_id": old_task_id,
                "last_state_transition": datetime.now(ZoneInfo("UTC"))
                - timedelta(days=10),
            }
        )
        storage._task_cache[old_task_id] = old_task

        # Create a recent completed task
        recent_task_id = str(uuid.uuid4())
        recent_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(hours=1)).isoformat(),
        )
        recent_task = recent_task.model_copy(update={"task_id": recent_task_id})
        storage._task_cache[recent_task_id] = recent_task

        # Cleanup tasks older than 7 days
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=7)
        deleted, failed = storage.cleanup_tasks(
            status=TaskStatus.COMPLETED.value, before_timestamp=cutoff
        )

        assert deleted == 1
        assert failed == 0

        # Old task should be gone
        assert storage.get_task(old_task_id) is None

        # Recent task should still exist
        assert storage.get_task(recent_task_id) is not None

    def test_cleanup_with_calendar_errors(self, storage):
        """Test cleanup handling of calendar deletion errors."""
        from openhab_semantic_mcp.monitoring.models import new_monitoring_task

        # Create two old tasks
        task1_id = str(uuid.uuid4())
        task1 = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(days=10)).isoformat(),
        )
        task1 = task1.model_copy(
            update={
                "task_id": task1_id,
                "last_state_transition": datetime.now(ZoneInfo("UTC"))
                - timedelta(days=10),
            }
        )
        storage._task_cache[task1_id] = task1

        task2_id = str(uuid.uuid4())
        task2 = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) - timedelta(days=10)).isoformat(),
        )
        task2 = task2.model_copy(
            update={
                "task_id": task2_id,
                "last_state_transition": datetime.now(ZoneInfo("UTC"))
                - timedelta(days=10),
            }
        )
        storage._task_cache[task2_id] = task2

        # Make first deletion succeed, second fail
        def delete_side_effect(task):
            if task.task_id == task1_id:
                return True
            raise CalDAVCalendarError("test_calendar", "delete", "Simulated error")

        storage.synchronizer.delete_event.side_effect = delete_side_effect

        # Cleanup
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=7)
        deleted, failed = storage.cleanup_tasks(
            status=TaskStatus.COMPLETED.value, before_timestamp=cutoff
        )

        assert deleted == 1
        assert failed == 1

        # First task should be gone
        assert storage.get_task(task1_id) is None

        # Second task should still be in cache (deletion failed)
        assert storage.get_task(task2_id) is not None


class TestCalDAVSynchronization:
    """Test CalDAV calendar synchronization."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")

    def test_sync_interval_disabled(self, mock_caldav_client):
        """Test that background sync is disabled when interval is 0."""
        config = create_caldav_config(sync_interval=0)

        with patch(
            "openhab_semantic_mcp.monitoring.backends.caldav.caldav.CalendarSynchronizer"
        ) as MockSync:
            mock_sync_instance = MockSync.return_value
            mock_sync_instance.sync_from_calendar.return_value = {}

            storage = CalDAVMonitoringStorage(config)

            # start_sync_worker should not be called when interval is 0
            mock_sync_instance.start_sync_worker.assert_not_called()


class TestCalDAVThreadSafety:
    """Test CalDAV thread safety."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")

    @pytest.fixture
    def storage(self, mock_caldav_client):
        """Create a CalDAV storage instance for testing."""
        config = create_caldav_config()

        with patch(
            "openhab_semantic_mcp.monitoring.backends.caldav.caldav.CalendarSynchronizer"
        ):
            storage = CalDAVMonitoringStorage(config)
            storage.synchronizer.create_event = Mock()
            storage.synchronizer.sync_from_calendar = Mock(return_value={})
            yield storage

    def test_concurrent_access_to_cache(self, storage):
        """Test that cache access is thread-safe."""
        import threading

        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task_ids = []

        def create_task():
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            storage.synchronizer.create_event.side_effect = lambda t: t.model_copy(
                update={"task_id": task_id}
            )
            storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        # Create tasks from multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=create_task)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All tasks should be in cache
        all_tasks = storage.get_all_tasks()
        assert len(all_tasks) >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
