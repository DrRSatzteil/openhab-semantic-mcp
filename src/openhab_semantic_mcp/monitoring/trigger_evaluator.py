"""Trigger evaluation logic for monitoring tasks."""

import datetime as dt
import logging
from typing import List

from .models import (
    MonitoringTask,
    MonitoringMode,
    TaskStatus,
    TaskUpdate,
    TriggerEvent,
    get_timezone_aware_datetime,
)
from ..exceptions import TriggerEvaluationError, MonitoringError, StorageError

logger = logging.getLogger(__name__)


class TriggerEvaluator:
    """Evaluates monitoring triggers and handles task logic."""

    def __init__(self, inventory, monitoring_store):

        self.inventory = inventory
        self.monitoring_store = monitoring_store
        self.timezone = monitoring_store.timezone

    def check_triggers(self, item_name: str, state_obj) -> List[TriggerEvent]:
        """Check monitoring triggers for an item state change (synchronous).

        Returns list of triggered events.
        """
        try:
            current_time = get_timezone_aware_datetime()
            active_tasks = self.monitoring_store.get_active_tasks()
            triggered_events = []

            for task_id, task in active_tasks.items():

                try:
                    if not self._item_matches_task(item_name, task):
                        continue

                    trigger_event = self._handle_trigger(
                        task, item_name, state_obj, current_time
                    )
                    if trigger_event:
                        # Return both event and task
                        triggered_events.append((trigger_event, task))

                except TriggerEvaluationError as e:
                    logger.error("Trigger evaluation error for task %s: %s", task_id, e)
                    continue
                except (MonitoringError, StorageError) as e:
                    logger.error(
                        "Monitoring/storage error processing task %s: %s", task_id, e
                    )
                    continue
                except Exception as e:
                    logger.error("Unexpected error processing task %s: %s", task_id, e)
                    continue

            logger.debug(
                "Monitoring trigger check completed for item=%s, triggers=%d",
                item_name,
                len(triggered_events),
            )
            return triggered_events

        except (TriggerEvaluationError, MonitoringError, StorageError) as e:
            logger.error("Error in check_triggers: %s", e)
            return []
        except Exception as e:
            logger.critical("Unexpected error in check_triggers: %s", e)
            raise

    def _item_matches_task(self, item_name: str, task: MonitoringTask) -> bool:
        """Check if an item matches the task's filters."""
        try:
            # Get items matching the filters
            if task.filters:
                matching_items = self.inventory.get(
                    location=task.filters.get("location"),
                    equipment=task.filters.get("equipment"),
                    point=task.filters.get("point"),
                    item_property=task.filters.get("property"),
                    state=task.filters.get("state"),
                    readonly=task.filters.get("readonly"),
                    invert_selection=task.filters.get("invert_selection"),
                    refinement_item_names=task.refinement,
                )
            else:
                matching_items = self.inventory.get(
                    refinement_item_names=task.refinement
                )

            # Check if current item matches
            return any(item == item_name for item in matching_items)

        except Exception as e:
            raise TriggerEvaluationError(task.task_id, item_name, str(e)) from e

    def _handle_trigger(
        self,
        task: MonitoringTask,
        item_name: str,
        state_obj,
        current_time: dt.datetime,
    ) -> TriggerEvent:
        """Handle a triggered event and return the trigger event."""
        try:
            # Create trigger event
            trigger_event = TriggerEvent(
                timestamp=current_time,
                item_name=item_name,
                item_state=str(state_obj.value),
                item_display_state=getattr(state_obj, "display_state", None),
                item_unit=getattr(state_obj, "unit", None),
            )

            # Update task
            task.triggered_count += 1
            task.last_triggered_at = current_time
            task.trigger_history.append(trigger_event.model_dump())

            # Update task status based on mode
            if task.mode == MonitoringMode.ONE_SHOT:
                # One-shot tasks complete after first trigger
                self._update_task_status(task.task_id, TaskStatus.COMPLETED)
            else:
                # Time window tasks remain active
                task_update = TaskUpdate(
                    triggered_count=task.triggered_count,
                    last_triggered_at=task.last_triggered_at,
                    trigger_history=task.trigger_history,
                )
                self.monitoring_store.update_task(task.task_id, task_update)

            logger.info("Task %s triggered by item %s", task.task_id, item_name)
            return trigger_event

        except (
            TriggerEvaluationError,
            MonitoringError,
            StorageError,
            ValueError,
            TypeError,
        ) as e:
            raise TriggerEvaluationError(task.task_id, item_name, str(e)) from e

    def _update_task_status(self, task_id: str, status: TaskStatus):
        """Update task status in storage."""
        try:
            update = TaskUpdate(status=status)
            self.monitoring_store.update_task(task_id, update)
        except Exception as e:
            logger.error("Failed to update task status %s: %s", task_id, e)
