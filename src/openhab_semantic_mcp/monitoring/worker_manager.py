"""Worker management for background threading operations."""

import threading
import logging

from .models import get_timezone_aware_datetime

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages background workers for monitoring operations."""

    def __init__(self, monitoring_store, monitoring_config, task_status_manager):
        self.monitoring_store = monitoring_store
        self.monitoring_config = monitoring_config
        self.task_status_manager = task_status_manager
        self.timezone = monitoring_config.timezone

        # Status update threading
        self._status_update_thread = None
        self._stop_status_update = threading.Event()

    def start_status_update_worker(self):
        """Start background status update worker."""
        self._status_update_thread = threading.Thread(
            target=self._status_update_worker, daemon=True
        )
        self._status_update_thread.start()
        logger.info("Started background status update worker")

    def stop_status_update_worker(self):
        """Stop the background status update worker."""
        self._stop_status_update.set()
        if self._status_update_thread and self._status_update_thread.is_alive():
            self._status_update_thread.join(timeout=5)
        logger.info("Stopped background status update worker")

    def _status_update_worker(self):
        """Background worker that updates task statuses based on time."""
        # Check every 60 seconds
        interval_seconds = 60

        while not self._stop_status_update.wait(interval_seconds):
            try:
                current_time = get_timezone_aware_datetime()
                all_tasks = self.monitoring_store.get_all_tasks()

                for task_id, task in all_tasks.items():
                    # Delegate status processing to TaskStatusManager
                    self.task_status_manager.process_task_time_based_transition(
                        task, current_time
                    )

            except (
                Exception
            ) as e:  # Background worker should never crash - log and continue
                logger.error("Error in status update worker: %s", e)
                # Continue running despite errors
