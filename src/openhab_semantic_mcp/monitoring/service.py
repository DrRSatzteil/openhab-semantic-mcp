"""Refactored monitoring service with component separation.

This version uses separate components for better maintainability and testability.
"""

import logging
import asyncio
from .interface import MonitoringStorageInterface
from .models import MonitoringTask, TriggerEvent, TaskUpdate, TaskStatus
from ..config import MonitoringConfig
from .trigger_evaluator import TriggerEvaluator
from .task_status_manager import TaskStatusManager
from .cleanup_manager import CleanupManager
from .worker_manager import WorkerManager
from .webhook_manager import WebhookManager

logger = logging.getLogger(__name__)


class MonitoringService:
    """Orchestrates monitoring operations using specialized components."""

    def __init__(
        self,
        monitoring_store: MonitoringStorageInterface,
        monitoring_config: MonitoringConfig,
        inventory,
    ):
        self.monitoring_store = monitoring_store
        self.monitoring_config = monitoring_config
        self.inventory = inventory

        # Initialize components
        self.trigger_evaluator = TriggerEvaluator(inventory, monitoring_store)
        self.task_status_manager = TaskStatusManager(monitoring_store)
        self.webhook_manager = WebhookManager(monitoring_config)
        self.cleanup_manager = CleanupManager(monitoring_store, monitoring_config)
        self.worker_manager = WorkerManager(
            monitoring_store, monitoring_config, self.task_status_manager
        )

        # Start background workers
        self._start_workers()

    def _start_workers(self):
        """Start all background workers."""
        self.cleanup_manager.start_cleanup_worker()
        self.worker_manager.start_status_update_worker()

    def create_monitoring_task(
        self,
        mode,
        filters=None,
        refinement=None,
        start_time=None,
        end_time=None,
    ) -> MonitoringTask:
        """Create a monitoring task by delegating to the backend storage."""
        return self.monitoring_store.create_task(
            mode=mode,
            filters=filters,
            refinement=refinement,
            start_time=start_time,
            end_time=end_time,
        )

    async def check_triggers_async(self, item_name: str, state_obj):
        """Check monitoring triggers for an item state change (asynchronous)."""
        try:
            # Use trigger evaluator to check for triggers and get matching tasks with events
            triggered_events = self.trigger_evaluator.check_triggers(
                item_name, state_obj
            )

            # Trigger webhooks directly for all triggered events
            if triggered_events:
                # Fire and forget - no need to wait for completion
                for trigger_event, task in triggered_events:
                    if task:
                        asyncio.create_task(
                            self._trigger_webhook_async(task, trigger_event)
                        )

        except (ValueError, RuntimeError, AttributeError) as e:
            logger.error("Error in check_triggers_async: %s", e)

    async def _trigger_webhook_async(
        self, task: MonitoringTask, trigger_event: TriggerEvent
    ):
        """Trigger webhook for a monitoring task (asynchronous)."""
        try:
            logger.info(
                "Task %s triggered by item %s", task.task_id, trigger_event.item_name
            )

            # Delegate webhook triggering to webhook manager
            await self.webhook_manager.trigger_webhook_async(task, trigger_event)

        except (ValueError, RuntimeError, AttributeError) as e:
            logger.error("Failed to trigger webhook for task %s: %s", task.task_id, e)
            self.task_status_manager.update_task_status(task.task_id, TaskStatus.ERROR)

    def shutdown(self):
        """Shutdown all background workers gracefully."""
        logger.info("Shutting down monitoring service...")

        self.cleanup_manager.stop_cleanup_worker()
        self.worker_manager.stop_status_update_worker()

        logger.info("Monitoring service shutdown complete")
