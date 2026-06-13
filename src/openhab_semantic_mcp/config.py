"""Centralized configuration for OpenHAB Semantic MCP Server."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class OpenHABConfig(BaseSettings):
    """OpenHAB connection configuration."""

    base_url: str = Field(
        default="http://localhost:8080",
        description="OpenHAB base URL",
    )
    api_token: Optional[str] = Field(
        default=None,
        description="OpenHAB API token for authentication",
    )

    model_config = SettingsConfigDict(
        env_prefix="OPENHAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class MCPConfig(BaseSettings):
    """MCP server configuration."""

    host: str = Field(
        default="0.0.0.0",
        description="Host to bind MCP server",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port for MCP server",
    )
    transport: str = Field(
        default="streamable-http",
        description="MCP transport mode",
    )

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class MonitoringConfig(BaseSettings):
    """Monitoring system configuration."""

    # Required fields
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook endpoint for monitoring notifications",
    )
    webhook_auth_header: Optional[str] = Field(
        default=None,
        description="Authorization header for webhook requests",
    )
    timezone: str = Field(
        default="UTC",
        description="Timezone for monitoring tasks (e.g., Europe/Berlin)",
    )

    # Storage configuration
    storage_type: str = Field(
        default="memory",
        description="Storage backend type (memory, file, caldav)",
    )
    storage_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Backend-specific configuration",
    )

    # Cleanup configuration
    cleanup_interval_minutes: int = Field(
        default=60,
        ge=1,
        description="Cleanup interval in minutes",
    )
    retain_completed_days: int = Field(
        default=7,
        ge=0,
        description="Days to retain completed tasks",
    )
    retain_cancelled_days: int = Field(
        default=3,
        ge=0,
        description="Days to retain cancelled tasks",
    )
    retain_error_days: int = Field(
        default=7,
        ge=0,
        description="Days to retain error tasks",
    )
    enable_auto_cleanup: bool = Field(
        default=True,
        description="Enable automatic cleanup of old tasks",
    )

    model_config = SettingsConfigDict(
        env_prefix="MONITORING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        if not v:
            return "UTC"
        try:
            ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{v}': {e}") from e
        return v

    @field_validator("storage_config", mode="before")
    @classmethod
    def parse_storage_config(cls, v: Any) -> Dict[str, Any]:
        """Parse storage config from JSON string if needed."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if not isinstance(parsed, dict):
                    logger.warning(
                        "MONITORING_STORAGE_CONFIG must be a JSON object, using empty config"
                    )
                    return {}
                return parsed
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse MONITORING_STORAGE_CONFIG: %s", e)
                return {}
        elif isinstance(v, dict):
            return v
        else:
            return {}


class InventoryConfig(BaseSettings):
    """Inventory configuration."""

    refresh_minutes: int = Field(
        default=60,
        ge=1,
        description="Inventory refresh interval in minutes",
    )

    model_config = SettingsConfigDict(
        env_prefix="INVENTORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ServerConfig(BaseSettings):
    """Complete server configuration."""

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Sub-configurations
    openhab: OpenHABConfig = Field(default_factory=OpenHABConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    inventory: InventoryConfig = Field(default_factory=InventoryConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def load_sub_configs(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Load sub-configurations from environment."""
        # Sub-configs will be loaded automatically by Pydantic
        if "openhab" not in values:
            values["openhab"] = OpenHABConfig()
        if "mcp" not in values:
            values["mcp"] = MCPConfig()
        if "monitoring" not in values:
            values["monitoring"] = MonitoringConfig()
        if "inventory" not in values:
            values["inventory"] = InventoryConfig()
        return values

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"Invalid log level '{v}'. Must be one of: {', '.join(valid_levels)}"
            )
        return v_upper


def load_config(env_file: Optional[Path] = None) -> ServerConfig:
    """
    Load and validate server configuration from environment.

    Args:
        env_file: Optional path to .env file. Defaults to .env in current directory.

    Returns:
        Validated ServerConfig instance

    Raises:
        ValueError: If configuration is invalid
    """
    if env_file and env_file.exists():
        logger.info("Loading configuration from %s", env_file)

    try:
        # ServerConfig and its nested BaseSettings models must all receive the
        # explicit env file so top-level and nested settings resolve from the
        # same source instead of falling back to the default .env location.
        env_kwargs: Dict[str, Any] = (
            {"_env_file": env_file} if env_file is not None else {}
        )

        config = ServerConfig(
            openhab=OpenHABConfig(**env_kwargs),
            mcp=MCPConfig(**env_kwargs),
            monitoring=MonitoringConfig(**env_kwargs),
            inventory=InventoryConfig(**env_kwargs),
            **env_kwargs,
        )
        logger.info("Configuration loaded and validated successfully")
        return config
    except Exception as e:
        logger.error("Configuration validation failed: %s", e)
        raise ValueError(f"Invalid configuration: {e}") from e
