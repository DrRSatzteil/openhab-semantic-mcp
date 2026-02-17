"""Tests for CalDAV calendar event mapper and synchronizer."""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from zoneinfo import ZoneInfo

import pytest

from openhab_semantic_mcp.monitoring.backends.caldav.calendar_event_mapper import (
    CalendarEventMapper,
)
from openhab_semantic_mcp.monitoring.backends.caldav.calendar_synchronizer import (
    CalendarSynchronizer,
)
from openhab_semantic_mcp.monitoring.backends.caldav.exceptions import (
    CalDAVConnectionError,
    CalDAVCalendarError,
    CalDAVEventError,
)
from openhab_semantic_mcp.monitoring.models import (
    MonitoringMode,
    MonitoringTask,
    TaskStatus,
    TimeWindow,
    new_monitoring_task,
    set_default_timezone,
)

# ============================================================
# Helpers
# ============================================================


def make_mock_event(task_data: dict, uid="test-uid-123", dtstart=None, dtend=None):
    """Build a mock CalDAV event whose vobject_instance holds *task_data* as JSON description."""
    now = datetime.now(ZoneInfo("UTC"))
    dtstart = dtstart or now
    dtend = dtend or now + timedelta(hours=1)

    vevent = Mock()
    vevent.description.value = json.dumps(task_data)
    vevent.dtstart.value = dtstart
    vevent.dtend.value = dtend

    # Component with dict-like .get() for UID (used by sync_from_calendar)
    component = MagicMock()
    component.get.side_effect = lambda key, default=None: (
        uid if key == "uid" else default
    )

    event = Mock()
    event.id = uid
    event.component = component
    event.vobject_instance.vevent = vevent
    return event


def make_task(task_id="test-task-id", **overrides):
    """Create a MonitoringTask for testing."""
    set_default_timezone("UTC")
    now = datetime.now(ZoneInfo("UTC"))
    defaults = dict(
        task_id=task_id,
        mode=MonitoringMode.ONE_SHOT,
        status=TaskStatus.ACTIVE,
        time_window=TimeWindow(start_time=now, end_time=now + timedelta(hours=1)),
        last_state_transition=now,
        created_at=now,
        filters={"location": "Indoor_Room_LivingRoom"},
    )
    defaults.update(overrides)
    return MonitoringTask(**defaults)


# ============================================================
# CalendarEventMapper
# ============================================================


class TestCleanSemanticName:
    """Test rule-based semantic name cleaning."""

    def test_full_semantic_name(self):
        assert (
            CalendarEventMapper.clean_semantic_name("Indoor_Room_LivingRoom")
            == "Living Room"
        )

    def test_single_word(self):
        assert CalendarEventMapper.clean_semantic_name("Temperature") == "Temperature"

    def test_camel_case_only(self):
        assert CalendarEventMapper.clean_semantic_name("OpenState") == "Open State"

    def test_empty_string(self):
        assert CalendarEventMapper.clean_semantic_name("") == ""

    def test_underscores_only(self):
        """Last part after underscore split is empty string."""
        assert CalendarEventMapper.clean_semantic_name("Foo_Bar_Baz") == "Baz"

    def test_abbreviation_stays_together(self):
        assert CalendarEventMapper.clean_semantic_name("HVAC") == "HVAC"

    def test_abbreviation_followed_by_word(self):
        assert CalendarEventMapper.clean_semantic_name("HVACThermostat") == "HVAC Thermostat"

    def test_word_followed_by_abbreviation(self):
        assert CalendarEventMapper.clean_semantic_name("myHVACUnit") == "my HVAC Unit"

    def test_abbreviation_in_semantic_path(self):
        assert CalendarEventMapper.clean_semantic_name("Equipment_HVACSystem") == "HVAC System"


class TestFormatStateValue:
    """Test state value formatting."""

    def test_none_returns_any(self):
        assert CalendarEventMapper.format_state_value(None) == "Any"

    def test_empty_dict_returns_any(self):
        assert CalendarEventMapper.format_state_value({}) == "Any"

    def test_exact_single(self):
        assert (
            CalendarEventMapper.format_state_value({"kind": "exact", "states": ["ON"]})
            == "ON"
        )

    def test_exact_multiple(self):
        result = CalendarEventMapper.format_state_value(
            {"kind": "exact", "states": ["ON", "OFF"]}
        )
        assert result == "ON,OFF"

    def test_range_both_bounds(self):
        result = CalendarEventMapper.format_state_value(
            {"kind": "range", "lowerBound": 20.0, "upperBound": 30.0}
        )
        assert result == "20.0-30.0"

    def test_range_lower_only(self):
        result = CalendarEventMapper.format_state_value(
            {"kind": "range", "lowerBound": 15.0}
        )
        assert result == ">15.0"

    def test_range_upper_only(self):
        result = CalendarEventMapper.format_state_value(
            {"kind": "range", "upperBound": 25.0}
        )
        assert result == "<25.0"

    def test_unknown_kind(self):
        assert CalendarEventMapper.format_state_value({"kind": "foo"}) == "Unknown"

    def test_exact_empty_states(self):
        assert (
            CalendarEventMapper.format_state_value({"kind": "exact", "states": []})
            == "Unknown"
        )


class TestGenerateCalendarTitle:
    """Test calendar title generation from task filters."""

    def test_location_only(self):
        task = make_task(filters={"location": "Indoor_Room_LivingRoom"})
        title = CalendarEventMapper.generate_calendar_title(task)
        assert "Living Room" in title

    def test_multiple_filters(self):
        task = make_task(
            filters={
                "location": "Indoor_Room_Kitchen",
                "point": "Measurement",
                "property": "Temperature",
            }
        )
        title = CalendarEventMapper.generate_calendar_title(task)
        assert "Kitchen" in title
        assert "Measurement" in title
        assert "Temperature" in title
        # Parts are joined by |
        assert "|" in title

    def test_equipment_filter(self):
        task = make_task(filters={"equipment": "HVAC_AirConditioner"})
        title = CalendarEventMapper.generate_calendar_title(task)
        assert "Air Conditioner" in title

    def test_state_filter(self):
        task = make_task(filters={"state": {"kind": "exact", "states": ["ON"]}})
        title = CalendarEventMapper.generate_calendar_title(task)
        assert "ON" in title

    def test_no_filters_uses_task_id(self):
        task = make_task(task_id="abcdef12-3456-7890-abcd-ef1234567890", filters={})
        title = CalendarEventMapper.generate_calendar_title(task)
        assert "abcdef12" in title


class TestParseEventToTask:
    """Test parsing CalDAV events into MonitoringTask objects."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_valid_event(self):
        """Parse a well-formed event with full task JSON in the description."""
        now = datetime.now(ZoneInfo("UTC"))
        task_data = {
            "mode": "one_shot",
            "status": "active",
            "last_state_transition": now.isoformat(),
            "created_at": now.isoformat(),
            "filters": {"location": "Indoor_Room_LivingRoom"},
        }

        event = make_mock_event(
            task_data,
            uid="uid-abc-123",
            dtstart=now,
            dtend=now + timedelta(hours=1),
        )

        task = CalendarEventMapper.parse_event_to_task(event)

        assert task is not None
        assert task.task_id == "uid-abc-123"
        assert task.mode == MonitoringMode.ONE_SHOT
        assert task.status == TaskStatus.ACTIVE

    def test_non_json_description_returns_none(self):
        """Events with plain-text descriptions should be silently skipped."""
        vevent = Mock()
        vevent.description.value = "Just a plain text note"

        event = Mock()
        event.id = "uid-plain"
        event.vobject_instance.vevent = vevent

        result = CalendarEventMapper.parse_event_to_task(event)
        assert result is None

    def test_no_description_returns_none(self):
        """Events without a description field should be skipped."""
        vevent = Mock(spec=[])  # no attributes at all
        vevent.description = None
        # getattr(vevent, "description", None) returns None → falsy

        event = Mock()
        event.id = "uid-nodesc"
        event.vobject_instance.vevent = vevent

        result = CalendarEventMapper.parse_event_to_task(event)
        assert result is None

    def test_invalid_task_data_raises(self):
        """If the JSON is valid but not a valid MonitoringTask, raise CalDAVEventError."""
        vevent = Mock()
        vevent.description.value = json.dumps({"mode": "invalid_mode_value"})
        vevent.dtstart.value = datetime.now(ZoneInfo("UTC"))
        vevent.dtend.value = datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)

        event = Mock()
        event.id = "uid-bad-data"
        event.vobject_instance.vevent = vevent

        with pytest.raises(CalDAVEventError):
            CalendarEventMapper.parse_event_to_task(event)


# ============================================================
# CalendarSynchronizer
# ============================================================


def make_synchronizer(connected=True, calendar_events=None):
    """Create a CalendarSynchronizer with a mocked connection."""
    connection = Mock()
    connection.is_connected.return_value = connected
    connection.config.url = "https://caldav.example.com"
    connection.config.calendar_name = "Test Calendar"

    calendar = MagicMock()
    calendar.date_search.return_value = calendar_events or []
    calendar.get_display_name.return_value = "Test Calendar"
    connection.get_calendar.return_value = calendar

    storage = Mock()
    storage.get_all_tasks.return_value = {}
    storage.delete_task = Mock()

    sync = CalendarSynchronizer(
        connection=connection,
        storage=storage,
        sync_interval=0,
        timezone="UTC",
    )
    return sync, connection, calendar, storage


class TestSyncFromCalendar:
    """Test calendar → local synchronization."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_sync_empty_calendar(self):
        sync, _, _, _ = make_synchronizer(calendar_events=[])

        result = sync.sync_from_calendar()

        assert result == {}

    def test_sync_valid_events(self):
        now = datetime.now(ZoneInfo("UTC"))
        task_data = {
            "mode": "one_shot",
            "status": "active",
            "last_state_transition": now.isoformat(),
            "created_at": now.isoformat(),
            "filters": {"location": "Indoor_Room_LivingRoom"},
        }
        event = make_mock_event(
            task_data, uid="uid-1", dtstart=now, dtend=now + timedelta(hours=1)
        )

        sync, _, _, _ = make_synchronizer(calendar_events=[event])

        result = sync.sync_from_calendar()

        assert "uid-1" in result
        assert result["uid-1"].task_id == "uid-1"

    def test_sync_skips_unparseable_events(self):
        """Events that fail to parse should be skipped, not crash the sync."""
        # One good event, one bad event
        now = datetime.now(ZoneInfo("UTC"))
        good_data = {
            "mode": "one_shot",
            "status": "active",
            "last_state_transition": now.isoformat(),
            "created_at": now.isoformat(),
        }
        good_event = make_mock_event(
            good_data, uid="uid-good", dtstart=now, dtend=now + timedelta(hours=1)
        )

        bad_event = Mock()
        bad_event.id = "uid-bad"
        bad_component = MagicMock()
        bad_component.get.side_effect = lambda key, default=None: (
            "uid-bad" if key == "uid" else default
        )
        bad_event.component = bad_component
        bad_event.vobject_instance.vevent.description.value = "not json"

        sync, _, _, _ = make_synchronizer(calendar_events=[good_event, bad_event])

        result = sync.sync_from_calendar()

        # Good event survives, bad one is skipped
        assert "uid-good" in result
        assert "uid-bad" not in result

    def test_sync_deletes_removed_tasks(self):
        """Tasks that exist locally but not in the calendar should be deleted."""
        sync, _, _, storage = make_synchronizer(calendar_events=[])
        storage.get_all_tasks.return_value = {
            "old-task-1": Mock(),
            "old-task-2": Mock(),
        }

        sync.sync_from_calendar()

        assert storage.delete_task.call_count == 2

    def test_sync_not_connected_raises(self):
        sync, _, _, _ = make_synchronizer(connected=False)

        with pytest.raises(CalDAVConnectionError):
            sync.sync_from_calendar()


class TestCreateEvent:
    """Test calendar event creation."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_create_event_success(self):
        sync, connection, calendar, _ = make_synchronizer()
        task = make_task(task_id=None)

        mock_event = Mock()
        mock_event.id = "new-uid-456"
        calendar.save_event.return_value = mock_event

        result = sync.create_event(task)

        assert result.task_id == "new-uid-456"
        calendar.save_event.assert_called_once()

    def test_create_event_not_connected(self):
        sync, _, _, _ = make_synchronizer(connected=False)
        task = make_task()

        with pytest.raises(CalDAVConnectionError):
            sync.create_event(task)

    def test_create_event_calendar_error(self):
        sync, _, calendar, _ = make_synchronizer()
        calendar.save_event.side_effect = Exception("Server error")
        task = make_task()

        with pytest.raises(CalDAVCalendarError):
            sync.create_event(task)

    def test_create_event_stores_task_data_as_json(self):
        """The event description should contain serialized task data."""
        sync, _, calendar, _ = make_synchronizer()
        task = make_task(task_id=None, filters={"location": "Indoor_Room_Kitchen"})

        mock_event = Mock()
        mock_event.id = "new-uid"
        calendar.save_event.return_value = mock_event

        sync.create_event(task)

        call_kwargs = calendar.save_event.call_args[1]
        description = call_kwargs["description"]
        parsed = json.loads(description)
        assert parsed["filters"]["location"] == "Indoor_Room_Kitchen"
        # task_id should be excluded from the description
        assert "task_id" not in parsed
        # datetime fields should be serialized as ISO strings, not raw objects
        assert isinstance(parsed["last_state_transition"], str)


class TestUpdateEvent:
    """Test calendar event updates."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_update_event_success(self):
        sync, _, calendar, _ = make_synchronizer()
        task = make_task()

        mock_event = Mock()
        mock_event.vobject_instance.vevent = Mock()
        mock_event.vobject_instance.vevent.summary = Mock()
        mock_event.vobject_instance.vevent.description = Mock()
        mock_event.vobject_instance.vevent.dtstart = Mock()
        mock_event.vobject_instance.vevent.dtend = Mock()
        calendar.event_by_uid.return_value = mock_event

        result = sync.update_event(task)

        assert result is not None
        mock_event.save.assert_called_once()

    def test_update_event_not_found(self):
        sync, _, calendar, _ = make_synchronizer()
        calendar.event_by_uid.return_value = None
        task = make_task()

        result = sync.update_event(task)

        assert result is None

    def test_update_event_not_connected(self):
        sync, _, _, _ = make_synchronizer(connected=False)
        task = make_task()

        with pytest.raises(CalDAVConnectionError):
            sync.update_event(task)

    def test_update_event_calendar_error(self):
        sync, _, calendar, _ = make_synchronizer()
        calendar.event_by_uid.side_effect = Exception("Server error")
        task = make_task()

        with pytest.raises(CalDAVCalendarError):
            sync.update_event(task)

    def test_update_event_converts_timezone(self):
        """dtstart/dtend should be converted to the configured timezone."""
        sync, _, calendar, _ = make_synchronizer()
        sync.timezone = "Europe/Berlin"

        task = make_task()

        mock_vevent = Mock()
        mock_vevent.summary = Mock()
        mock_vevent.description = Mock()
        mock_vevent.dtstart = Mock()
        mock_vevent.dtend = Mock()

        mock_event = Mock()
        mock_event.vobject_instance.vevent = mock_vevent
        calendar.event_by_uid.return_value = mock_event

        sync.update_event(task)

        # The dtstart value should have been converted to Europe/Berlin
        set_value = mock_vevent.dtstart.value
        assert set_value.tzinfo is not None


class TestDeleteEvent:
    """Test calendar event deletion."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_delete_event_success(self):
        sync, _, calendar, _ = make_synchronizer()
        task = make_task()

        mock_event = Mock()
        calendar.event_by_uid.return_value = mock_event

        result = sync.delete_event(task)

        assert result is True
        mock_event.delete.assert_called_once()

    def test_delete_event_not_found_still_returns_true(self):
        """If the event doesn't exist, deletion is considered successful."""
        sync, _, calendar, _ = make_synchronizer()
        calendar.event_by_uid.return_value = None
        task = make_task()

        result = sync.delete_event(task)

        assert result is True

    def test_delete_event_not_connected(self):
        sync, _, _, _ = make_synchronizer(connected=False)
        task = make_task()

        with pytest.raises(CalDAVConnectionError):
            sync.delete_event(task)

    def test_delete_event_calendar_error(self):
        sync, _, calendar, _ = make_synchronizer()
        calendar.event_by_uid.side_effect = Exception("Server error")
        task = make_task()

        with pytest.raises(CalDAVCalendarError):
            sync.delete_event(task)


class TestSyncWorkerLifecycle:
    """Test background sync worker start/stop."""

    def setup_method(self):
        set_default_timezone("UTC")

    def test_start_worker_with_zero_interval_does_nothing(self):
        sync, _, _, _ = make_synchronizer()
        sync.sync_interval = 0

        sync.start_sync_worker()

        assert sync._thread is None

    def test_start_and_stop_worker(self):
        sync, _, _, _ = make_synchronizer()
        sync.sync_interval = 60

        sync.start_sync_worker()
        assert sync._thread is not None
        assert sync._thread.is_alive()

        sync.stop_sync_worker()
        assert not sync._thread.is_alive()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
