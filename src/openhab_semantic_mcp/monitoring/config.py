"""Monitoring configuration."""

from dataclasses import dataclass, field
from typing import Any, Dict
import zoneinfo


@dataclass
class MonitoringConfig:
    """Configuration for monitoring system."""

    webhook_url: str
    webhook_auth_header: str
    storage_type: str
    timezone: str
    storage_config: Dict[str, Any] = field(default_factory=dict)

    # Cleanup configuration
    cleanup_interval_minutes: int = 60  # How often to run cleanup (default: 1 hour)
    retain_completed_days: int = 7  # How long to keep completed tasks
    retain_cancelled_days: int = 3  # How long to keep cancelled tasks
    retain_error_days: int = 7  # How long to keep error tasks
    enable_auto_cleanup: bool = True  # Whether to run automatic cleanup

    def __post_init__(self):
        """Validate timezone on startup."""
        if not self.timezone:
            raise ValueError("MONITORING_TIMEZONE environment variable is required")

        # Validate timezone format
        try:
            zoneinfo.ZoneInfo(self.timezone)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{self.timezone}': {e}") from e
