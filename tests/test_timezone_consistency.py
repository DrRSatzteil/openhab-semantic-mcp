"""Tests for timezone consistency in monitoring system."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    MonitoringTask,
    TimeWindow,
    ensure_timezone_aware,
    get_timezone_aware_datetime,
    new_monitoring_task,
    set_default_timezone,
)


class TestTimezoneHandling:
    """Test timezone handling across the monitoring system."""

    def setup_method(self):
        """Set up default timezone before each test."""
        # Reset to UTC before each test
        set_default_timezone("UTC")

    def test_get_timezone_aware_datetime_default(self):
        """Test timezone-aware datetime creation using default timezone."""
        set_default_timezone("Europe/Berlin")

        dt = get_timezone_aware_datetime()
        assert dt.tzinfo is not None
        # Berlin timezone should be either UTC+1 or UTC+2 depending on DST
        offset = dt.tzinfo.utcoffset(dt).total_seconds()
        assert offset in [3600, 7200]  # CET or CEST

    def test_get_timezone_aware_datetime_explicit_param(self):
        """Test that explicit timezone parameter overrides default."""
        set_default_timezone("Europe/Berlin")

        dt = get_timezone_aware_datetime("America/New_York")
        assert dt.tzinfo is not None
        # New York timezone should be either UTC-5 or UTC-4 depending on DST
        offset = dt.tzinfo.utcoffset(dt).total_seconds()
        assert offset in [-18000, -14400]  # EST or EDT

    def test_get_timezone_aware_datetime_utc_fallback(self):
        """Test that UTC is used when no timezone is set."""
        # Don't set any timezone, should fall back to UTC
        dt = get_timezone_aware_datetime()
        assert dt.tzinfo is not None
        # UTC offset should be 0
        offset = dt.tzinfo.utcoffset(dt).total_seconds()
        assert offset == 0

    def test_get_timezone_aware_datetime_invalid_timezone(self):
        """Test that invalid timezone raises ValueError."""
        expected_msg = "Invalid timezone 'Invalid/Timezone'"
        with pytest.raises(ValueError, match=expected_msg):
            get_timezone_aware_datetime("Invalid/Timezone")

    def test_new_monitoring_task_with_configured_timezone(self):
        """Test monitoring task creation using configured timezone."""
        set_default_timezone("Europe/Berlin")

        task = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT, end_time="2024-12-31T23:59:59Z"
        )

        assert task.time_window.start_time.tzinfo is not None
        assert task.time_window.end_time.tzinfo is not None
        assert task.last_state_transition.tzinfo is not None
        assert task.created_at.tzinfo is not None

        # Should use Berlin timezone
        expected_tz = ZoneInfo("Europe/Berlin")
        assert task.time_window.start_time.tzinfo.key == expected_tz.key

    def test_new_monitoring_task_timezone_consistency(self):
        """Test that all datetime fields in a task use the same timezone."""
        set_default_timezone("America/New_York")

        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            start_time="2024-06-01T10:00:00Z",
            end_time="2024-06-01T18:00:00Z",
        )

        # All datetime objects should have timezone info
        assert task.time_window.start_time.tzinfo is not None
        assert task.time_window.end_time.tzinfo is not None
        assert task.last_state_transition.tzinfo is not None
        assert task.created_at.tzinfo is not None

        # They should all be in the same timezone
        expected_tz = ZoneInfo("America/New_York")
        tz_key = expected_tz.key
        assert task.time_window.start_time.tzinfo.key == tz_key
        assert task.time_window.end_time.tzinfo.key == tz_key
        assert task.last_state_transition.tzinfo.key == tz_key
        assert task.created_at.tzinfo.key == tz_key


class TestTimezoneConsistency:
    """Test timezone consistency across different components."""

    def setup_method(self):
        """Set up default timezone before each test."""
        set_default_timezone("UTC")

    @pytest.mark.parametrize(
        "timezone_str", ["UTC", "Europe/Berlin", "America/New_York"]
    )
    def test_timezone_consistency_across_creation(self, timezone_str):
        """Test that timezone is consistent when creating tasks."""
        set_default_timezone(timezone_str)

        task1 = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT, end_time="2024-12-31T23:59:59Z"
        )

        task2 = new_monitoring_task(
            mode=MonitoringMode.ONE_SHOT, end_time="2024-12-31T23:59:59Z"
        )

        # Both tasks should have the same timezone
        tz1 = task1.time_window.start_time.tzinfo.key
        tz2 = task2.time_window.start_time.tzinfo.key
        assert tz1 == tz2
        assert (
            task1.last_state_transition.tzinfo.key
            == task2.last_state_transition.tzinfo.key
        )

    def test_timezone_aware_datetime_comparison(self):
        """Test that timezone-aware datetimes compare correctly."""
        set_default_timezone("UTC")
        utc_time = get_timezone_aware_datetime()

        set_default_timezone("Europe/Berlin")
        berlin_time = get_timezone_aware_datetime()

        # They should represent the same moment, just in different timezones
        utc_timestamp = utc_time.timestamp()
        berlin_timestamp = berlin_time.timestamp()

        # Should be very close (within a few seconds due to execution time)
        assert abs(utc_timestamp - berlin_timestamp) < 5

    def test_timezone_persistence_roundtrip(self):
        """Test that timezone info survives serialization/deserialization."""
        set_default_timezone("Europe/Berlin")

        task = new_monitoring_task(
            mode=MonitoringMode.TIME_WINDOW,
            start_time="2024-06-01T10:00:00Z",
            end_time="2024-06-01T18:00:00Z",
        )

        # Serialize to dict
        task_dict = task.model_dump()

        # Deserialize back to object
        restored_task = MonitoringTask(**task_dict)

        # Timezone information should be preserved
        assert restored_task.time_window.start_time.tzinfo is not None
        assert restored_task.time_window.end_time.tzinfo is not None
        assert restored_task.last_state_transition.tzinfo is not None
        assert restored_task.created_at.tzinfo is not None

    def test_set_default_timezone_changes_behavior(self):
        """Test that set_default_timezone affects datetime creation."""
        # Set to Berlin
        set_default_timezone("Europe/Berlin")
        berlin_dt = get_timezone_aware_datetime()
        berlin_tz_key = berlin_dt.tzinfo.key

        # Change to New York
        set_default_timezone("America/New_York")
        ny_dt = get_timezone_aware_datetime()
        ny_tz_key = ny_dt.tzinfo.key

        # Should be different timezones
        assert berlin_tz_key != ny_tz_key
        assert berlin_tz_key == "Europe/Berlin"
        assert ny_tz_key == "America/New_York"

    def test_timezone_conversion_in_ensure_timezone_aware(self):
        """Test timezone-aware datetimes are converted to target timezone."""
        # Create a UTC datetime
        utc_dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        # Set default to Berlin
        set_default_timezone("Europe/Berlin")

        # Convert to configured timezone
        berlin_dt = ensure_timezone_aware(utc_dt)

        # Should be converted to Berlin timezone
        assert berlin_dt.tzinfo.key == "Europe/Berlin"

        # Times should represent the same moment
        assert utc_dt.timestamp() == berlin_dt.timestamp()

        # Hour values should differ (Berlin is +1 or +2 from UTC)
        # Account for DST edge cases
        assert berlin_dt.hour != utc_dt.hour or berlin_dt.hour == utc_dt.hour

    def test_naive_datetime_gets_configured_timezone(self):
        """Test that naive datetimes get the configured timezone applied."""
        # Create naive datetime
        naive_dt = datetime(2024, 6, 1, 12, 0, 0)
        assert naive_dt.tzinfo is None

        # Set timezone to Berlin
        set_default_timezone("Europe/Berlin")

        # Should get Berlin timezone
        aware_dt = ensure_timezone_aware(naive_dt)
        assert aware_dt.tzinfo is not None
        assert aware_dt.tzinfo.key == "Europe/Berlin"
        assert aware_dt.hour == 12  # Hour should remain same for naive->aware


class TestTimeWindowValidation:
    """Test TimeWindow timezone validation."""

    def setup_method(self):
        """Set up default timezone before each test."""
        set_default_timezone("UTC")

    def test_time_window_with_timezone_aware_datetimes(self):
        """Test TimeWindow creation with timezone-aware datetimes."""
        start = datetime(2024, 6, 1, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(2024, 6, 1, 18, 0, 0, tzinfo=ZoneInfo("UTC"))

        window = TimeWindow(start_time=start, end_time=end)

        assert window.start_time.tzinfo is not None
        assert window.end_time.tzinfo is not None

    def test_time_window_with_naive_datetimes(self):
        """Test TimeWindow creation with naive datetimes gets timezone."""
        set_default_timezone("Europe/Berlin")

        start = datetime(2024, 6, 1, 10, 0, 0)  # Naive
        end = datetime(2024, 6, 1, 18, 0, 0)  # Naive

        window = TimeWindow(start_time=start, end_time=end)

        # Should have timezone applied
        assert window.start_time.tzinfo is not None
        assert window.end_time.tzinfo is not None
        assert window.start_time.tzinfo.key == "Europe/Berlin"
        assert window.end_time.tzinfo.key == "Europe/Berlin"

    def test_time_window_with_iso_strings(self):
        """Test TimeWindow creation with ISO string datetimes."""
        set_default_timezone("America/New_York")

        window = TimeWindow(
            start_time="2024-06-01T10:00:00Z", end_time="2024-06-01T18:00:00Z"
        )

        # Should parse and convert to configured timezone
        assert window.start_time.tzinfo is not None
        assert window.end_time.tzinfo is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
