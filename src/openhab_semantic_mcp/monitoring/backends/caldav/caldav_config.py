"""Configuration management for CalDAV monitoring backend."""

from dataclasses import dataclass


@dataclass
class CalDAVConfig:
    """Configuration for CalDAV monitoring storage backend."""

    url: str
    username: str
    password: str
    calendar_name: str = "Monitoring"
    sync_interval: int = 0

    @classmethod
    def from_dict(cls, config: dict) -> "CalDAVConfig":
        """Create CalDAVConfig from dictionary configuration."""
        return cls(
            url=config.get("url", ""),
            username=config.get("username", ""),
            password=config.get("password", ""),
            calendar_name=config.get("calendar_name", "Monitoring"),
            sync_interval=config.get("sync_interval", 0),
        )

    def validate(self) -> None:
        """Validate configuration parameters."""
        if not self.url:
            raise ValueError("CalDAV URL is required")
        if not self.username:
            raise ValueError("CalDAV username is required")
        if not self.password:
            raise ValueError("CalDAV password is required")
