"""CalDAV-specific exceptions."""

from ....exceptions import StorageError


class CalDAVError(StorageError):
    """CalDAV-specific error."""


class CalDAVConnectionError(CalDAVError):
    """CalDAV connection failed."""

    def __init__(self, url: str, reason: str):
        super().__init__(
            f"CalDAV connection failed to '{url}': {reason}", "CALDAV_CONNECTION_ERROR"
        )
        self.url = url
        self.reason = reason
        self.details.update({"url": url, "reason": reason})


class CalDAVCalendarError(CalDAVError):
    """CalDAV calendar operation failed."""

    def __init__(self, calendar_name: str, operation: str, reason: str):
        super().__init__(
            f"CalDAV calendar '{calendar_name}' {operation} failed: {reason}",
            "CALDAV_CALENDAR_ERROR",
        )
        self.calendar_name = calendar_name
        self.operation = operation
        self.reason = reason
        self.details.update(
            {"calendar_name": calendar_name, "operation": operation, "reason": reason}
        )


class CalDAVEventError(CalDAVError):
    """CalDAV event operation failed."""

    def __init__(self, task_id: str, operation: str, reason: str):
        super().__init__(
            f"CalDAV event {operation} failed for task '{task_id}': {reason}",
            "CALDAV_EVENT_ERROR",
        )
        self.task_id = task_id
        self.operation = operation
        self.reason = reason
        self.details.update(
            {"task_id": task_id, "operation": operation, "reason": reason}
        )
