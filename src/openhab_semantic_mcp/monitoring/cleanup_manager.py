"""Cleanup management for monitoring tasks."""

import datetime as dt
import threading
import logging
from typing import Dict

from .models import (
    get_timezone_aware_datetime,
)

logger = logging.getLogger(__name__)


class CleanupManager:
    """Manages cleanup operations for monitoring tasks."""

    def __init__(self, monitoring_store, monitoring_config):
        self.monitoring_store = monitoring_store
        self.monitoring_config = monitoring_config
        self.timezone = monitoring_config.timezone

        # Cleanup threading
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()

    def start_cleanup_worker(self):
        """Start background cleanup worker if enabled."""
        if self.monitoring_config.enable_auto_cleanup:
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_worker, daemon=True
            )
            self._cleanup_thread.start()
            logger.info("Started background cleanup worker")

    def stop_cleanup_worker(self):
        """Stop the background cleanup worker."""
        self._stop_cleanup.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        logger.info("Stopped background cleanup worker")

    def _cleanup_worker(self):
        """Background worker that performs periodic cleanup."""
        interval_seconds = self.monitoring_config.cleanup_interval_minutes * 60

        while not self._stop_cleanup.wait(interval_seconds):
            try:
                self.perform_cleanup()
            except Exception as e:
                # Cleanup worker should never crash - log and continue
                logger.error("Error in cleanup worker: %s", e)

    def perform_cleanup(self) -> Dict[str, int]:
        """Perform comprehensive cleanup of old monitoring tasks."""
        try:
            current_time = get_timezone_aware_datetime()

            cleanup_stats: Dict[str, int] = {
                "total": 0,
            }

            # Definition der zu bereinigenden Status + Retention-Konfig
            cleanup_config = {
                "completed": self.monitoring_config.retain_completed_days,
                "cancelled": self.monitoring_config.retain_cancelled_days,
                "error": self.monitoring_config.retain_error_days,
            }

            for status, retention_days in cleanup_config.items():
                cutoff = current_time - dt.timedelta(days=retention_days)

                cleaned, failed = self.monitoring_store.cleanup_tasks(status, cutoff)

                cleanup_stats[status] = cleaned
                cleanup_stats[f"{status}_failed"] = failed
                cleanup_stats["total"] += cleaned

            total_failed = sum(
                value for key, value in cleanup_stats.items() if key.endswith("_failed")
            )

            if cleanup_stats["total"] > 0:
                logger.info(
                    "Cleanup completed: %d tasks deleted "
                    "(%d completed, %d cancelled, %d error) | %d failed",
                    cleanup_stats["total"],
                    cleanup_stats.get("completed", 0),
                    cleanup_stats.get("cancelled", 0),
                    cleanup_stats.get("error", 0),
                    total_failed,
                )

            elif total_failed > 0:
                logger.warning(
                    "Cleanup finished with no successful deletions, "
                    "but %d deletions failed.",
                    total_failed,
                )

            else:
                logger.debug("Cleanup finished: nothing to delete.")

            return cleanup_stats

        except RuntimeError as e:
            logger.error("Error during cleanup: %s", e)
            return {
                "completed": 0,
                "cancelled": 0,
                "error": 0,
                "total": 0,
            }
