"""Data models for monitoring tasks and configurations."""

import zoneinfo

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# Module-level timezone cache (set by config on initialization)
# Falls back to env var for backward compatibility
_DEFAULT_TIMEZONE: Optional[str] = None


def set_default_timezone(timezone: str) -> None:
    """Set the default timezone for monitoring operations.

    This should be called once during application initialization.
    """
    global _DEFAULT_TIMEZONE
    _DEFAULT_TIMEZONE = timezone


def _get_default_timezone() -> str:
    """Get the default timezone, with fallback to UTC."""
    return _DEFAULT_TIMEZONE or "UTC"


def ensure_timezone_aware(v, tz_str: Optional[str] = None) -> datetime:
    """Ensure a datetime value is timezone-aware."""
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if isinstance(v, datetime):
        if v.tzinfo is None:
            # Timezone-naive: use specified or default timezone
            tz_str = tz_str or _get_default_timezone()
            return v.replace(tzinfo=zoneinfo.ZoneInfo(tz_str))
        else:
            # Timezone-aware: convert to specified or default timezone
            tz_str = tz_str or _get_default_timezone()
            target_tz = zoneinfo.ZoneInfo(tz_str)
            return v.astimezone(target_tz)
    return v


def get_timezone_aware_datetime(tz_str: Optional[str] = None) -> datetime:
    """Get timezone-aware datetime instance.

    Args:
        tz_str: Optional timezone string. Falls back to default timezone.

    Returns:
        Timezone-aware datetime

    Raises:
        ValueError: If timezone is invalid.
    """
    timezone_str = tz_str or _get_default_timezone()
    if not timezone_str:
        raise ValueError("Timezone is required")

    try:
        tz = zoneinfo.ZoneInfo(timezone_str)
        return datetime.now(tz)
    except Exception as e:
        raise ValueError(f"Invalid timezone '{timezone_str}': {e}") from e


class MonitoringMode(str, Enum):
    """Monitoring task modes."""

    ONE_SHOT = "one_shot"  # Trigger once and finish
    TIME_WINDOW = "time_window"  # Monitor for time period, can trigger multiple times


class PriorityLevel(str, Enum):
    """Priority levels for monitoring tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    """Monitoring task status states."""

    PENDING = "pending"  # Waiting for start time (time_window mode)
    ACTIVE = "active"  # Currently monitoring
    COMPLETED = "completed"  # Finished (one_shot) or time window ended
    CANCELLED = "cancelled"  # Manually cancelled
    ERROR = "error"  # System error


class TimeWindow(BaseModel):
    """Time window for monitoring tasks."""

    start_time: datetime = Field(..., description="When monitoring should start")
    end_time: datetime = Field(..., description="When monitoring should end")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def validate_timezone(cls, v):
        """Ensure a datetime value is timezone-aware."""
        return ensure_timezone_aware(v)

    class Config:
        use_enum_values = True


class MonitoringIntent(BaseModel):
    """Intent context for monitoring tasks."""

    requested_by: str = Field(
        ..., 
        description="Human-readable name of user who requested this monitoring task"
    )
    
    action: str = Field(
        ..., 
        max_length=500,
        description="Action to perform when this monitoring task triggers (free text)"
    )
    
    context: Optional[str] = Field(
        None, 
        max_length=500,
        description="Additional context or instructions for handling the trigger"
    )
    
    priority: PriorityLevel = Field(
        PriorityLevel.MEDIUM,
        description="Priority of the task. MUST be exactly one of: 'low', 'medium', 'high', 'critical' (or 'normal' for 'medium')"
    )

    @field_validator("priority", mode="before")
    @classmethod
    def coerce_priority_from_string(cls, v):
        """Auto-coerce string priority to enum, handling synonyms."""
        if isinstance(v, str):
            # Handle synonyms
            if v.lower() == "normal":
                v = "medium"
            
            # Convert string to enum, case-insensitive
            try:
                return PriorityLevel(v.lower())
            except ValueError:
                raise ValueError(f"Priority must be one of: {', '.join([p.value for p in PriorityLevel])} (or 'normal' for 'medium')")
        return v

    class Config:
        """Pydantic configuration."""
        pass


class TaskUpdate(BaseModel):
    """Model for monitoring task updates."""

    status: Optional[TaskStatus] = None
    time_window: Optional["TimeWindowUpdate"] = None
    filters: Optional[Dict[str, Any]] = None
    refinement: Optional[Dict[str, Any]] = None
    intent: Optional[MonitoringIntent] = None
    triggered_count: Optional[int] = None
    last_triggered_at: Optional[datetime] = None
    last_state_transition: Optional[datetime] = None
    trigger_history: Optional[List[Dict[str, Any]]] = None
    update_state_transition: Optional[bool] = Field(
        default=True,
        description="Whether to update last_state_transition when status changes",
    )

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class TimeWindowUpdate(BaseModel):
    """Model for time window updates."""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class MonitoringTask(BaseModel):
    """Complete monitoring task configuration."""

    task_id: Optional[str] = None
    mode: MonitoringMode
    status: TaskStatus
    time_window: TimeWindow
    last_state_transition: datetime  # When task entered current status
    created_at: Optional[datetime] = None  # When task was created

    # What to monitor
    filters: Optional[Dict[str, Any]] = None
    refinement: Optional[List[str]] = None

    # Intent context
    intent: Optional[MonitoringIntent] = None

    # Tracking
    triggered_count: int = 0
    last_triggered_at: Optional[datetime] = None
    trigger_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Backend-specific metadata (e.g., CalDAV event info, file paths, etc.)
    backend_metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic configuration."""

        use_enum_values = True

    def apply_updates(
        self,
        updates: TaskUpdate,
    ) -> "MonitoringTask":
        """Apply updates to the task."""

        update_data = updates.model_dump(exclude_unset=True)
        update_state_transition = update_data.pop("update_state_transition", False)

        if "time_window" in update_data:
            update_data["time_window"] = self.time_window.model_copy(
                update=update_data["time_window"]
            )

        if update_state_transition and "status" in update_data:
            update_data["last_state_transition"] = get_timezone_aware_datetime()

        return self.model_copy(update=update_data)

    @field_validator(
        "last_state_transition", "created_at", "last_triggered_at", mode="before"
    )
    @classmethod
    def validate_timezone(cls, v):
        """Ensure a datetime value is timezone-aware."""
        if v is None:
            return v
        return ensure_timezone_aware(v)


class TriggerEvent(BaseModel):
    """Individual trigger event record."""

    timestamp: datetime
    item_name: str
    item_state: str
    item_display_state: Optional[str] = None
    item_unit: Optional[str] = None

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


def new_monitoring_task(
    mode: MonitoringMode,
    filters: Optional[Dict[str, Any]] = None,
    refinement: Optional[List[str]] = None,
    intent: Optional[MonitoringIntent] = None,
    start_time: Optional[str] = None,
    end_time: str = None,
) -> MonitoringTask:
    """Create a monitoring task."""

    now = get_timezone_aware_datetime()

    actual_start = ensure_timezone_aware(
        datetime.fromisoformat(start_time.replace("Z", "+00:00")) if start_time else now
    )
    actual_end = ensure_timezone_aware(
        datetime.fromisoformat(end_time.replace("Z", "+00:00")) if end_time else None
    )

    if not actual_end:
        raise ValueError("end_time is required")

    if now < actual_start:
        status = TaskStatus.PENDING
    elif now > actual_end:
        status = TaskStatus.COMPLETED
    else:
        status = TaskStatus.ACTIVE

    return MonitoringTask(
        task_id=None,
        mode=mode,
        status=status,
        time_window=TimeWindow(start_time=actual_start, end_time=actual_end),
        last_state_transition=now,
        created_at=now,
        filters=filters,
        refinement=refinement,
        intent=intent,
    )
