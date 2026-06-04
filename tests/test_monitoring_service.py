"""Tests for monitoring service layer components."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from openhab_semantic_mcp.dto import Item, State, Location
from openhab_semantic_mcp.inventory import Inventory
from openhab_semantic_mcp.monitoring.backends.memory import MemoryMonitoringStorage
from openhab_semantic_mcp.config import MonitoringConfig
from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    TaskStatus,
    TriggerEvent,
    new_monitoring_task,
    set_default_timezone,
)
from openhab_semantic_mcp.monitoring.trigger_evaluator import TriggerEvaluator
from openhab_semantic_mcp.monitoring.task_status_manager import TaskStatusManager
from openhab_semantic_mcp.monitoring.webhook_manager import WebhookManager
from openhab_semantic_mcp.monitoring.cleanup_manager import CleanupManager
from openhab_semantic_mcp.monitoring.service import MonitoringService


def create_test_config(**kwargs):
    """Helper to create test MonitoringConfig."""
    defaults = {
        "webhook_url": "https://test.example.com/webhook",
        "webhook_auth_header": "Authorization: Bearer test-token",
        "storage_type": "memory",
        "timezone": "UTC",
        "cleanup_interval_minutes": 60,
        "retain_completed_days": 7,
        "retain_cancelled_days": 3,
        "retain_error_days": 7,
        "enable_auto_cleanup": False,  # Disabled by default for tests
    }
    defaults.update(kwargs)
    return MonitoringConfig(**defaults)


def create_test_inventory():
    """Create a test inventory with sample items."""
    inventory = Inventory()

    # Create locations
    living_room = Location(
        name="Indoor_Room_LivingRoom", label="Living Room", short_name="LivingRoom"
    )
    kitchen = Location(
        name="Indoor_Room_Kitchen", label="Kitchen", short_name="Kitchen"
    )

    items = [
        Item(
            name="LivingRoom_Temperature",
            type="Number",
            state=State(value="21.5 °C"),
            location=living_room,
            point="Measurement",
            property="Temperature",
        ),
        Item(
            name="LivingRoom_Light",
            type="Switch",
            state=State(value="ON"),
            location=living_room,
            point="Control",
            property="Light",
        ),
        Item(
            name="Kitchen_Temperature",
            type="Number",
            state=State(value="22.0 °C"),
            location=kitchen,
            point="Measurement",
            property="Temperature",
        ),
    ]

    inventory.initialize_inventory(items)
    return inventory


class TestTriggerEvaluator:
    """Test trigger evaluation logic."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")
        self.config = create_test_config()
        self.storage = MemoryMonitoringStorage({"timezone": self.config.timezone})
        self.inventory = create_test_inventory()
        self.evaluator = TriggerEvaluator(self.inventory, self.storage)

    def test_item_matches_task_with_filters(self):
        """Test matching items to task filters."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        # Should match living room item
        assert self.evaluator._item_matches_task("LivingRoom_Temperature", task)
        assert self.evaluator._item_matches_task("LivingRoom_Light", task)

        # Should not match kitchen item
        assert not self.evaluator._item_matches_task("Kitchen_Temperature", task)

    def test_item_matches_task_with_refinement(self):
        """Test matching items with refinement."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            refinement=["LivingRoom_Temperature"],
        )

        # Should match only the refined item
        assert self.evaluator._item_matches_task("LivingRoom_Temperature", task)
        assert not self.evaluator._item_matches_task("LivingRoom_Light", task)

    def test_check_triggers_one_shot_mode(self):
        """Test trigger checking for one-shot mode."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        state_obj = Mock(value="22.0 °C", display_state="22.0 °C", unit="°C")

        # Trigger the task
        triggered_events = self.evaluator.check_triggers(
            "LivingRoom_Temperature", state_obj
        )

        assert len(triggered_events) == 1
        trigger_event, triggered_task = triggered_events[0]
        assert trigger_event.item_name == "LivingRoom_Temperature"
        assert trigger_event.item_state == "22.0 °C"

        # Task should be completed after one trigger
        updated_task = self.storage.get_task(task.task_id)
        assert updated_task.status == TaskStatus.COMPLETED

    def test_check_triggers_time_window_mode(self):
        """Test trigger checking for time window mode."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        state_obj = Mock(value="ON", display_state=None, unit=None)

        # First trigger
        triggered_events = self.evaluator.check_triggers("LivingRoom_Light", state_obj)
        assert len(triggered_events) == 1

        # Task should still be active
        updated_task = self.storage.get_task(task.task_id)
        assert updated_task.status == TaskStatus.ACTIVE
        assert updated_task.triggered_count == 1

        # Second trigger
        triggered_events = self.evaluator.check_triggers("LivingRoom_Light", state_obj)
        assert len(triggered_events) == 1

        # Task should still be active with increased count
        updated_task = self.storage.get_task(task.task_id)
        assert updated_task.status == TaskStatus.ACTIVE
        assert updated_task.triggered_count == 2

    def test_check_triggers_no_match(self):
        """Test trigger checking when item doesn't match."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_Kitchen"},
        )

        state_obj = Mock(value="ON")

        # Living room item shouldn't trigger kitchen filter
        triggered_events = self.evaluator.check_triggers("LivingRoom_Light", state_obj)
        assert len(triggered_events) == 0

    def test_check_triggers_multiple_tasks(self):
        """Test triggering multiple tasks."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        # Create two tasks that match the same item
        self.storage.create_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        self.storage.create_task(
            mode=MonitoringMode.TIME_WINDOW,
            end_time=end_time,
            filters={"point": "Control"},
        )

        state_obj = Mock(value="ON", display_state=None, unit=None)

        # Both tasks should trigger
        triggered_events = self.evaluator.check_triggers("LivingRoom_Light", state_obj)
        assert len(triggered_events) == 2


class TestTaskStatusManager:
    """Test task status management."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")
        self.config = create_test_config()
        self.storage = MemoryMonitoringStorage({"timezone": self.config.timezone})
        self.manager = TaskStatusManager(self.storage)

    def test_update_task_status(self):
        """Test updating task status."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.storage.create_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)

        assert task.status == TaskStatus.ACTIVE

        # Update to completed
        self.manager.update_task_status(task.task_id, TaskStatus.COMPLETED)

        updated_task = self.storage.get_task(task.task_id)
        assert updated_task.status == TaskStatus.COMPLETED

    def test_process_task_time_based_transition_to_active(self):
        """Test transitioning pending task to active."""
        now = datetime.now(ZoneInfo("UTC"))
        start_time = (now - timedelta(minutes=5)).isoformat()
        end_time = (now + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW, start_time=start_time, end_time=end_time
        )
        task = task.model_copy(
            update={"task_id": "test-task", "status": TaskStatus.PENDING}
        )
        self.storage.tasks["test-task"] = task

        # Process transition
        self.manager.process_task_time_based_transition(task, now)

        updated_task = self.storage.get_task("test-task")
        assert updated_task.status == TaskStatus.ACTIVE

    def test_process_task_time_based_transition_to_completed(self):
        """Test transitioning active task to completed."""
        now = datetime.now(ZoneInfo("UTC"))
        start_time = (now - timedelta(hours=2)).isoformat()
        end_time = (now - timedelta(minutes=5)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW, start_time=start_time, end_time=end_time
        )
        task = task.model_copy(
            update={"task_id": "test-task", "status": TaskStatus.ACTIVE}
        )
        self.storage.tasks["test-task"] = task

        # Process transition
        self.manager.process_task_time_based_transition(task, now)

        updated_task = self.storage.get_task("test-task")
        assert updated_task.status == TaskStatus.COMPLETED

    def test_process_task_time_based_transition_skips_terminal_states(self):
        """Test that terminal states are not changed."""
        now = datetime.now(ZoneInfo("UTC"))
        end_time = (now - timedelta(hours=1)).isoformat()

        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)
        task = task.model_copy(
            update={"task_id": "test-task", "status": TaskStatus.CANCELLED}
        )
        self.storage.tasks["test-task"] = task

        # Process transition - should not change cancelled status
        self.manager.process_task_time_based_transition(task, now)

        updated_task = self.storage.get_task("test-task")
        assert updated_task.status == TaskStatus.CANCELLED


class TestWebhookManager:
    """Test webhook management."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")
        self.config = create_test_config()
        self.manager = WebhookManager(self.config)

    def test_build_webhook_payload(self):
        """Test building webhook payload."""
        now = datetime.now(ZoneInfo("UTC"))
        end_time = (now + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )
        task = task.model_copy(update={"task_id": "test-task", "triggered_count": 1})

        trigger_event = TriggerEvent(
            timestamp=now,
            item_name="LivingRoom_Light",
            item_state="ON",
            item_display_state="ON",
            item_unit=None,
        )

        payload = self.manager._build_webhook_payload(task, trigger_event)

        assert payload["task_id"] == "test-task"
        assert payload["mode"] == MonitoringMode.ONE_SHOT
        assert payload["trigger_count"] == 1
        assert payload["item"]["name"] == "LivingRoom_Light"
        assert payload["item"]["state"] == "ON"
        assert "time_window" in payload

    @pytest.mark.asyncio
    async def test_trigger_webhook_async_success(self):
        """Test successful webhook trigger."""
        now = datetime.now(ZoneInfo("UTC"))
        end_time = (now + timedelta(hours=1)).isoformat()

        task = new_monitoring_task(mode=MonitoringMode.ONE_SHOT, end_time=end_time)
        task = task.model_copy(update={"task_id": "test-task"})

        trigger_event = TriggerEvent(
            timestamp=now, item_name="LivingRoom_Light", item_state="ON"
        )

        # Mock aiohttp session
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_post = AsyncMock(return_value=mock_response)
            mock_session.return_value.__aenter__.return_value.post = mock_post
            mock_session.return_value.__aexit__ = AsyncMock()

            await self.manager.trigger_webhook_async(task, trigger_event)

            # Verify webhook was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == self.config.webhook_url

    @pytest.mark.asyncio
    async def test_trigger_webhook_async_no_url(self):
        """Test webhook trigger with no URL configured."""
        config = create_test_config(webhook_url=None)
        manager = WebhookManager(config)

        now = datetime.now(ZoneInfo("UTC"))
        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(now + timedelta(hours=1)).isoformat(),
        )
        task = task.model_copy(update={"task_id": "test-task"})

        trigger_event = TriggerEvent(timestamp=now, item_name="Test", item_state="ON")

        # Should return early without error
        await manager.trigger_webhook_async(task, trigger_event)

    def test_apply_webhook_auth_header(self):
        """Test applying webhook authentication header."""
        headers = {"Content-Type": "application/json"}

        self.manager._apply_webhook_auth_header(headers)

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-token"

    def test_apply_webhook_auth_header_invalid_format(self):
        """Test handling invalid auth header format."""
        config = create_test_config(webhook_auth_header="InvalidFormat")
        manager = WebhookManager(config)

        headers = {"Content-Type": "application/json"}
        manager._apply_webhook_auth_header(headers)

        # Should not add invalid header
        assert "InvalidFormat" not in headers


class TestCleanupManager:
    """Test cleanup management."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")
        self.config = create_test_config(enable_auto_cleanup=False)
        self.storage = MemoryMonitoringStorage({"timezone": self.config.timezone})
        self.manager = CleanupManager(self.storage, self.config)

    def test_perform_cleanup(self):
        """Test performing cleanup."""
        now = datetime.now(ZoneInfo("UTC"))

        # Create old completed task
        old_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(now - timedelta(days=10)).isoformat(),
        )
        old_task = old_task.model_copy(
            update={
                "task_id": "old-task",
                "last_state_transition": now - timedelta(days=10),
            }
        )
        self.storage.tasks["old-task"] = old_task

        # Create recent completed task
        recent_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(now - timedelta(hours=1)).isoformat(),
        )
        recent_task = recent_task.model_copy(update={"task_id": "recent-task"})
        self.storage.tasks["recent-task"] = recent_task

        # Perform cleanup
        stats = self.manager.perform_cleanup()

        # Old task should be cleaned up
        assert self.storage.get_task("old-task") is None
        assert self.storage.get_task("recent-task") is not None

        # Check stats
        assert stats["completed"] == 1
        assert stats["total"] == 1

    def test_perform_cleanup_multiple_statuses(self):
        """Test cleanup of multiple status types."""
        now = datetime.now(ZoneInfo("UTC"))

        # Create old cancelled task
        cancelled_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT, end_time=(now - timedelta(days=5)).isoformat()
        )
        cancelled_task = cancelled_task.model_copy(
            update={
                "task_id": "cancelled-task",
                "status": TaskStatus.CANCELLED,
                "last_state_transition": now - timedelta(days=5),
            }
        )
        self.storage.tasks["cancelled-task"] = cancelled_task

        # Create old error task
        error_task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=(now - timedelta(days=10)).isoformat(),
        )
        error_task = error_task.model_copy(
            update={
                "task_id": "error-task",
                "status": TaskStatus.ERROR,
                "last_state_transition": now - timedelta(days=10),
            }
        )
        self.storage.tasks["error-task"] = error_task

        # Perform cleanup
        stats = self.manager.perform_cleanup()

        # Both should be cleaned up
        assert self.storage.get_task("cancelled-task") is None
        assert self.storage.get_task("error-task") is None
        assert stats["cancelled"] == 1
        assert stats["error"] == 1
        assert stats["total"] == 2


class TestMonitoringService:
    """Test monitoring service integration."""

    def setup_method(self):
        """Set up test environment."""
        set_default_timezone("UTC")
        self.config = create_test_config(enable_auto_cleanup=False)
        self.storage = MemoryMonitoringStorage({"timezone": self.config.timezone})
        self.inventory = create_test_inventory()

        # Create service
        self.service = MonitoringService(self.storage, self.config, self.inventory)

    def teardown_method(self):
        """Clean up after tests."""
        self.service.shutdown()

    def test_create_monitoring_task(self):
        """Test creating monitoring task through service."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        task = self.service.create_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        assert task.task_id is not None
        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.filters["location"] == "Indoor_Room_LivingRoom"

    @pytest.mark.asyncio
    async def test_check_triggers_async(self):
        """Test async trigger checking."""
        end_time = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()

        self.service.create_monitoring_task(
            mode=MonitoringMode.ONE_SHOT,
            end_time=end_time,
            filters={"location": "Indoor_Room_LivingRoom"},
        )

        state_obj = Mock(value="ON", display_state=None, unit=None)

        # Mock webhook manager
        with patch.object(
            self.service.webhook_manager, "trigger_webhook_async", new=AsyncMock()
        ) as mock_webhook:
            await self.service.check_triggers_async("LivingRoom_Light", state_obj)

            # Give async tasks time to execute
            await asyncio.sleep(0.1)

            # Webhook should have been called
            assert mock_webhook.call_count > 0

    @pytest.mark.asyncio
    async def test_check_triggers_async_error_handling(self):
        """Test error handling in async trigger checking."""
        state_obj = Mock(value="ON")

        # Trigger with no tasks should not raise error
        await self.service.check_triggers_async("NonExistent_Item", state_obj)

    def test_service_components_initialized(self):
        """Test that all service components are properly initialized."""
        assert self.service.trigger_evaluator is not None
        assert self.service.task_status_manager is not None
        assert self.service.webhook_manager is not None
        assert self.service.cleanup_manager is not None
        assert self.service.worker_manager is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
