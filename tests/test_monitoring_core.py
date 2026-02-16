"""Tests for monitoring system core functionality."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    MonitoringTask,
    TaskStatus,
    TaskUpdate,
    TimeWindow,
    get_timezone_aware_datetime,
    new_monitoring_task,
    set_default_timezone,
)


class TestMonitoringTaskCreation:
    """Test monitoring task creation and validation."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_create_one_shot_task_immediate(self):
        """Test creating a one-shot task that starts immediately."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.status == TaskStatus.ACTIVE
        assert task.time_window.end_time.tzinfo is not None
        assert task.triggered_count == 0
        assert task.last_triggered_at is None

    def test_create_one_shot_task_future_start(self):
        """Test creating a one-shot task that starts in the future."""
        now = datetime.now(ZoneInfo("UTC"))
        start_time = (now + timedelta(hours=1)).isoformat()
        end_time = (now + timedelta(hours=2)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT, start_time=start_time, end_time=end_time
        )

        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.status == TaskStatus.PENDING
        assert task.time_window.start_time > get_timezone_aware_datetime()

    def test_create_time_window_task(self):
        """Test creating a time window task."""
        now = datetime.now(ZoneInfo("UTC"))
        start_time = now.isoformat()
        end_time = (now + timedelta(hours=2)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW, start_time=start_time, end_time=end_time
        )

        assert task.mode == MonitoringMode.TIME_WINDOW
        assert task.status == TaskStatus.ACTIVE
        assert task.triggered_count == 0

    def test_create_task_with_filters(self):
        """Test creating task with item filters."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom", "point": "Measurement"},
        )

        assert task.filters == {
            "location": "Indoor_Room_LivingRoom",
            "point": "Measurement",
        }

    def test_create_task_with_refinement(self):
        """Test creating task with item name refinement."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            refinement=["LivingRoom_Light", "Kitchen_Temperature"],
        )

        assert task.refinement == ["LivingRoom_Light", "Kitchen_Temperature"]

    def test_create_task_already_ended(self):
        """Test creating task with end time in the past."""
        now = datetime.now(ZoneInfo("UTC"))
        end_time = (now - timedelta(hours=1)).isoformat()

        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.status == TaskStatus.COMPLETED

    def test_create_task_requires_end_time(self):
        """Test that end_time is required."""
        with pytest.raises(ValueError, match="end_time is required"):
            new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=None)

    def test_task_timestamps_are_timezone_aware(self):
        """Test that all task timestamps are timezone-aware."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.time_window.start_time.tzinfo is not None
        assert task.time_window.end_time.tzinfo is not None
        assert task.created_at.tzinfo is not None
        assert task.last_state_transition.tzinfo is not None


class TestTaskUpdates:
    """Test monitoring task update operations."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_update_task_status(self):
        """Test updating task status."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        updates = TaskUpdate(status=TaskStatus.CANCELLED, update_state_transition=True)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.CANCELLED
        assert updated_task.last_state_transition > task.last_state_transition

    def test_update_task_without_state_transition(self):
        """Test updating task without updating state transition time."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        original_transition = task.last_state_transition

        updates = TaskUpdate(status=TaskStatus.COMPLETED, update_state_transition=False)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.last_state_transition == original_transition

    def test_update_triggered_count(self):
        """Test updating triggered count."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = new_monitoring_task(mode=MonitoringMode.TIME_WINDOW, end_time=end_time)

        updates = TaskUpdate(triggered_count=1)
        updated_task = task.apply_updates(updates)

        assert updated_task.triggered_count == 1

    def test_update_time_window(self):
        """Test updating task time window."""
        now = datetime.now(ZoneInfo("UTC"))
        end_time = (now + timedelta(hours=1)).isoformat()
        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        new_end = now + timedelta(hours=2)
        updates = TaskUpdate(time_window={"end_time": new_end})
        updated_task = task.apply_updates(updates)

        assert updated_task.time_window.end_time.hour == new_end.hour

    def test_update_filters(self):
        """Test updating task filters."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Kitchen"},
        )

        updates = TaskUpdate(filters={"location": "LivingRoom"})
        updated_task = task.apply_updates(updates)

        assert updated_task.filters == {"location": "LivingRoom"}


class TestTaskStatusTransitions:
    """Test monitoring task status state machine."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_pending_to_active_transition(self):
        """Test PENDING → ACTIVE status transition."""
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            start_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=2)).isoformat(),
        )

        assert task.status == TaskStatus.PENDING

        updates = TaskUpdate(status=TaskStatus.ACTIVE, update_state_transition=True)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.ACTIVE

    def test_active_to_completed_transition(self):
        """Test ACTIVE → COMPLETED status transition."""
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        assert task.status == TaskStatus.ACTIVE

        updates = TaskUpdate(status=TaskStatus.COMPLETED, update_state_transition=True)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.COMPLETED

    def test_active_to_cancelled_transition(self):
        """Test ACTIVE → CANCELLED status transition."""
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        updates = TaskUpdate(status=TaskStatus.CANCELLED, update_state_transition=True)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.CANCELLED

    def test_active_to_error_transition(self):
        """Test ACTIVE → ERROR status transition."""
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        updates = TaskUpdate(status=TaskStatus.ERROR, update_state_transition=True)
        updated_task = task.apply_updates(updates)

        assert updated_task.status == TaskStatus.ERROR


class TestTimeWindowValidation:
    """Test time window validation and behavior."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_time_window_start_before_end(self):
        """Test that time window start is before end."""
        now = datetime.now(ZoneInfo("UTC"))
        start = now
        end = now + timedelta(hours=1)

        window = TimeWindow(start_time=start, end_time=end)

        assert window.start_time < window.end_time

    def test_time_window_with_timezone_conversion(self):
        """Test time window with different timezone input."""
        set_default_timezone("America/New_York")

        utc_time = datetime.now(ZoneInfo("UTC"))
        window = TimeWindow(start_time=utc_time, end_time=utc_time + timedelta(hours=1))

        # Should be converted to configured timezone
        assert window.start_time.tzinfo.key == "America/New_York"
        assert window.end_time.tzinfo.key == "America/New_York"


class TestTaskTriggerTracking:
    """Test task trigger event tracking."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_trigger_count_increments(self):
        """Test that triggered_count increments correctly."""
        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        assert task.triggered_count == 0

        updates = TaskUpdate(triggered_count=task.triggered_count + 1)
        task = task.apply_updates(updates)

        assert task.triggered_count == 1

    def test_last_triggered_at_updates(self):
        """Test that last_triggered_at updates."""
        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        assert task.last_triggered_at is None

        now = get_timezone_aware_datetime()
        updates = TaskUpdate(triggered_count=1, last_triggered_at=now)
        task = task.apply_updates(updates)

        assert task.last_triggered_at is not None
        assert task.last_triggered_at.tzinfo is not None

    def test_trigger_history_appends(self):
        """Test that trigger history accumulates events."""
        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        assert len(task.trigger_history) == 0

        event = {
            "timestamp": get_timezone_aware_datetime().isoformat(),
            "item_name": "TestItem",
            "item_state": "ON",
        }

        updates = TaskUpdate(trigger_history=[event])
        task = task.apply_updates(updates)

        assert len(task.trigger_history) == 1
        assert task.trigger_history[0]["item_name"] == "TestItem"


class TestTaskSerialization:
    """Test task serialization and deserialization."""

    def setup_method(self):
        """Set up timezone before each test."""
        set_default_timezone("UTC")

    def test_task_serialization_roundtrip(self):
        """Test that task can be serialized and deserialized."""
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
            filters={"location": "Kitchen"},
            refinement=["LivingRoom_Light"],
        )

        # Serialize
        task_dict = task.model_dump()

        # Deserialize
        restored_task = MonitoringTask(**task_dict)

        assert restored_task.mode == task.mode
        assert restored_task.status == task.status
        assert restored_task.filters == task.filters
        assert restored_task.refinement == task.refinement
        assert restored_task.time_window.start_time == task.time_window.start_time

    def test_task_json_serialization(self):
        """Test that task can be serialized to JSON."""
        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=(datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat(),
        )

        json_str = task.model_dump_json()

        assert isinstance(json_str, str)
        assert "mode" in json_str
        assert "status" in json_str
        assert "time_window" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
