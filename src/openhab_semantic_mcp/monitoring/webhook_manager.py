"""Webhook management for monitoring operations."""

import logging
from typing import Dict
import aiohttp

from .models import MonitoringTask, TriggerEvent

logger = logging.getLogger(__name__)


class WebhookManager:
    """Manages webhook operations for monitoring tasks."""

    def __init__(self, monitoring_config):
        self.monitoring_config = monitoring_config

    def _build_webhook_payload(
        self, task: MonitoringTask, trigger_event: TriggerEvent
    ) -> Dict:
        """Build webhook payload for task trigger."""
        payload = {
            "task_id": task.task_id,
            "mode": task.mode,
            "triggered_at": trigger_event.timestamp.isoformat(),
            "trigger_count": task.triggered_count,
            "item": {
                "name": trigger_event.item_name,
                "state": trigger_event.item_state,
                "display_state": trigger_event.item_display_state,
                "unit": trigger_event.item_unit,
            },
            "task_config": {
                "filters": task.filters,
                "refinement": task.refinement,
                "last_state_transition": task.last_state_transition.isoformat(),
            },
        }

        # Add time window info if applicable
        if task.time_window:
            payload["time_window"] = {
                "start_time": task.time_window.start_time.isoformat(),
                "end_time": task.time_window.end_time.isoformat(),
            }

        return payload

    async def trigger_webhook_async(
        self, task: MonitoringTask, trigger_event: TriggerEvent
    ):
        """Trigger webhook for a monitoring task (asynchronous)."""
        webhook_url = self.monitoring_config.webhook_url
        if not webhook_url:
            logger.warning("No webhook URL configured for task %s", task.task_id)
            return

        # Prepare webhook payload
        payload = self._build_webhook_payload(task, trigger_event)

        # Prepare headers
        headers = {"Content-Type": "application/json"}
        self._apply_webhook_auth_header(headers)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    logger.info(
                        "Webhook triggered successfully for task %s", task.task_id
                    )

        except aiohttp.ClientError as e:
            logger.error("Failed to send webhook for task %s: %s", task.task_id, e)

    def _apply_webhook_auth_header(self, headers: Dict[str, str]) -> None:
        """Apply webhook authentication header if configured."""
        auth_header = self.monitoring_config.webhook_auth_header
        if auth_header:
            try:
                if ": " in auth_header:
                    key, value = auth_header.split(": ", 1)
                    headers[key] = value
                    logger.debug("Applied webhook auth header: %s", key)
                else:
                    logger.warning(
                        "Invalid webhook auth header format, expected 'Key: Value'"
                    )
            except ValueError as e:
                logger.warning("Failed to parse webhook auth header: %s", e)
