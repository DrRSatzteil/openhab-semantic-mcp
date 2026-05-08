#!/usr/bin/env python3
"""openHAB Semantic MCP Server bootstrap and runtime management."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Coroutine, Literal, Optional, cast

from mcp.server.fastmcp import FastMCP

from .config import ServerConfig, load_config
from .inventory import Inventory
from .monitoring.models import set_default_timezone
from .monitoring.tools import register as register_monitoring_tools
from .openhab_client import OpenHAB
from .tools.commands import register as register_command_tools
from .tools.discovery import register as register_discovery_tools
from .tools.inventory import register as register_inventory_tools

logger = logging.getLogger(__name__)


class AsyncEventDispatcher:
    """Dedicated dispatcher for async tasks from SSE callbacks."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._shutdown_lock = threading.Lock()
        self._closed = False
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def dispatch(self, coro: Coroutine[Any, Any, Any]) -> Future[Any]:
        """Dispatch an async task to the dispatcher."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _handle_result(result_future: Any) -> None:
            try:
                result_future.result()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Async task failed: %s", exc)

        future.add_done_callback(_handle_result)
        return future

    def shutdown(self) -> None:
        """Shut down the dispatcher."""
        with self._shutdown_lock:
            if self._closed:
                return
            self._closed = True

            if self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

            self._thread.join(timeout=10)

            if not self._loop.is_closed():
                self._loop.close()


class RuntimeManager:
    """Manages runtime initialization state and service references."""

    def __init__(self) -> None:
        self._initialized = False
        self._lock = threading.Lock()
        self._refresh_stop_event = threading.Event()
        self._refresh_thread: Optional[threading.Thread] = None
        self.dispatcher: Optional[AsyncEventDispatcher] = None
        self.monitoring_service: Any = None

    def initialize_if_needed(
        self,
        openhab_client: OpenHAB,
        inventory_manager: Inventory,
        refresh_minutes: int,
    ) -> None:
        """Initialize the runtime if needed."""
        with self._lock:
            if self._initialized:
                return

            self._refresh_stop_event.clear()
            self.dispatcher = AsyncEventDispatcher()

            try:
                items = openhab_client.get_semantic_points()
                inventory_manager.initialize_inventory(items)
                openhab_client.start_sse_listener(
                    self._make_sse_callback(inventory_manager),
                    [item.name for item in items],
                )
                logger.info("Loaded %s semantic points into inventory", len(items))
            except Exception as exc:
                logger.error("Failed to load semantic points: %s", exc)

            self._refresh_thread = threading.Thread(
                target=self._inventory_refresh_worker,
                args=(openhab_client, inventory_manager, refresh_minutes),
                daemon=True,
            )
            self._refresh_thread.start()
            logger.info(
                "Inventory refresh thread started (interval: %s minutes)",
                refresh_minutes,
            )
            self._initialized = True

    def _make_sse_callback(self, inventory_manager: Inventory) -> Any:
        """Create SSE callback with closure over inventory_manager."""

        def sse_callback(item_name: str, state_obj: Any) -> None:
            try:
                logger.debug(
                    "SSE callback triggered: item=%s, state=%s",
                    item_name,
                    state_obj.value,
                )

                item = inventory_manager.get_item(item_name)
                if item and item.state and item.state.value == state_obj.value:
                    return

                inventory_manager.update_state_index(item_name, state_obj)

                if self.monitoring_service is not None and self.dispatcher is not None:
                    self.dispatcher.dispatch(
                        self.monitoring_service.check_triggers_async(
                            item_name, state_obj
                        )
                    )
            except Exception as exc:
                logger.error("Error in SSE callback: %s", exc)

        return sse_callback

    def _inventory_refresh_worker(
        self,
        openhab_client: OpenHAB,
        inventory_manager: Inventory,
        refresh_minutes: int,
    ) -> None:
        """Background worker to periodically refresh the inventory."""
        interval_seconds = refresh_minutes * 60

        while not self._refresh_stop_event.wait(interval_seconds):
            try:
                logger.info("Starting scheduled inventory refresh...")
                items = openhab_client.get_semantic_points()

                if items:
                    try:
                        inventory_manager.initialize_inventory(items)
                        item_names = [item.name for item in items]
                        openhab_client.update_sse_items(item_names)
                        logger.info(
                            "Inventory refresh completed: %s items loaded",
                            len(items),
                        )
                    except Exception as init_error:
                        logger.error("Failed to update inventory: %s", init_error)
                        logger.warning(
                            "Inventory update failed – consider manual restart if needed"
                        )
                else:
                    logger.warning(
                        "No items received from OpenHAB - keeping existing inventory"
                    )
            except Exception as exc:
                logger.error("Failed to refresh inventory: %s", exc)
                logger.warning(
                    "Inventory refresh failed – consider manual restart if needed"
                )

    def shutdown(self) -> None:
        """Shut down runtime-managed background resources."""
        with self._lock:
            if not self._initialized:
                return

            refresh_thread = self._refresh_thread
            dispatcher = self.dispatcher
            self._initialized = False
            self._refresh_stop_event.set()
            self._refresh_thread = None
            self.dispatcher = None

        if refresh_thread and refresh_thread.is_alive():
            refresh_thread.join(timeout=10)

        if dispatcher is not None:
            dispatcher.shutdown()


@dataclass
class ServerApplication:
    """Fully wired application runtime."""

    config: ServerConfig
    mcp: FastMCP
    openhab: OpenHAB
    inventory: Inventory
    runtime_manager: RuntimeManager
    monitoring_service: Any
    _shutdown_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _shutdown_complete: bool = field(default=False, init=False, repr=False)

    def initialize(self) -> None:
        """Initialize runtime services before serving requests."""
        self.runtime_manager.initialize_if_needed(
            self.openhab,
            self.inventory,
            self.config.inventory.refresh_minutes,
        )

    def shutdown(self) -> None:
        """Shut down all application-managed resources exactly once."""
        with self._shutdown_lock:
            if self._shutdown_complete:
                return
            self._shutdown_complete = True

        try:
            self.openhab.stop_sse_listener()
            logger.info("SSE listener stopped")
        except Exception as exc:
            logger.error("Error stopping SSE listener during shutdown: %s", exc)

        try:
            self.runtime_manager.shutdown()
            logger.info("Runtime manager stopped")
        except Exception as exc:
            logger.error("Error stopping runtime manager during shutdown: %s", exc)

        try:
            if self.monitoring_service is not None:
                self.monitoring_service.shutdown()
                logger.info("Monitoring service stopped")
        except Exception as exc:
            logger.error("Error stopping monitoring service during shutdown: %s", exc)


def configure_logging(log_level: str) -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def bootstrap_application(env_file: Optional[Path] = None) -> ServerApplication:
    """Create the fully wired server application."""
    config = load_config(env_file=env_file)
    configure_logging(config.log_level)
    set_default_timezone(config.monitoring.timezone)

    logger.info("Configuration loaded successfully")
    logger.info("OpenHAB URL: %s", config.openhab.base_url)
    logger.info("MCP Server: %s:%d", config.mcp.host, config.mcp.port)
    logger.info("Monitoring Storage: %s", config.monitoring.storage_type)
    logger.info("Monitoring Timezone: %s", config.monitoring.timezone)

    log_level = cast(
        Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        config.log_level,
    )
    mcp = FastMCP(
        "OpenHAB Semantic MCP Server",
        host=config.mcp.host,
        port=config.mcp.port,
        log_level=log_level,
        json_response=True,
    )
    openhab = OpenHAB(config.openhab.base_url, api_token=config.openhab.api_token)
    inventory = Inventory()
    runtime_manager = RuntimeManager()

    register_discovery_tools(mcp, inventory=inventory)
    register_command_tools(mcp, openhab=openhab, inventory=inventory)
    register_inventory_tools(mcp, inventory=inventory)
    monitoring_service = register_monitoring_tools(
        mcp,
        monitoring_config=config.monitoring,
        inventory=inventory,
    )
    runtime_manager.monitoring_service = monitoring_service

    return ServerApplication(
        config=config,
        mcp=mcp,
        openhab=openhab,
        inventory=inventory,
        runtime_manager=runtime_manager,
        monitoring_service=monitoring_service,
    )


def run_server(app: Optional[ServerApplication] = None) -> ServerApplication:
    """Run the MCP server."""
    server_app = app or bootstrap_application()

    try:
        server_app.initialize()
        transport = cast(
            Literal["stdio", "sse", "streamable-http"],
            server_app.config.mcp.transport,
        )
        logger.info(
            "Starting openHAB Semantic MCP Server on %s:%s",
            server_app.config.mcp.host,
            server_app.config.mcp.port,
        )
        logger.info("Connected to OpenHAB at %s", server_app.config.openhab.base_url)
        logger.info("Using MCP transport: %s", transport)
        server_app.mcp.run(transport=transport)
    except Exception as exc:
        logger.error("Server error: %s", exc)
        raise
    finally:
        server_app.shutdown()

    return server_app


if __name__ == "__main__":
    run_server()
