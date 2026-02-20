#!/usr/bin/env python3
"""openHAB Semantic MCP Server - A lightweight MCP server for openHAB semantic operations."""

import asyncio
import logging
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .inventory import Inventory
from .openhab_client import OpenHAB
from .tools.commands import register as register_command_tools
from .tools.discovery import register as register_discovery_tools
from .tools.inventory import register as register_inventory_tools
from .monitoring.tools import register as register_monitoring_tools
from .monitoring.models import set_default_timezone

# ============================================================
# Configuration
# ============================================================
# Load and validate configuration (fails fast on startup if invalid)
config = load_config(env_file=Path(".env"))

# Initialize timezone for monitoring models
set_default_timezone(config.monitoring.timezone)

# Setup logging based on config
logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("Configuration loaded successfully")
logger.info("OpenHAB URL: %s", config.openhab.base_url)
logger.info("MCP Server: %s:%d", config.mcp.host, config.mcp.port)
logger.info("Monitoring Storage: %s", config.monitoring.storage_type)
logger.info("Monitoring Timezone: %s", config.monitoring.timezone)

# ============================================================
# Initialize core components
# ============================================================
mcp = FastMCP(
    "OpenHAB Semantic MCP Server",
    host=config.mcp.host,
    port=config.mcp.port,
    log_level=config.log_level,
    json_response=True,
)
openhab = OpenHAB(config.openhab.base_url, api_token=config.openhab.api_token)
inventory = Inventory()


# ============================================================
# AsyncEventDispatcher
# ============================================================
class AsyncEventDispatcher:
    """Dedicated dispatcher for async tasks from SSE callbacks."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def dispatch(self, coro):
        """Dispatch an async task to the dispatcher."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _handle_result(f):
            try:
                f.result()
            except Exception as e:
                logger.exception("Async task failed: %s", e)

        future.add_done_callback(_handle_result)
        return future

    def shutdown(self):
        """Shut down the dispatcher."""
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
        self._loop.close()


# ============================================================
# Runtime Manager
# ============================================================
class RuntimeManager:
    """Manages runtime initialization state and service references."""

    def __init__(self):
        self._initialized = False
        self._lock = threading.Lock()
        self.dispatcher: AsyncEventDispatcher = None
        self.monitoring_service = None

    def initialize_if_needed(self, openhab_client, inventory_manager):
        """Initialize the runtime if needed."""
        with self._lock:
            if self._initialized:
                return

            self.dispatcher = AsyncEventDispatcher()

            try:
                items = openhab_client.get_semantic_points()
                inventory_manager.initialize_inventory(items)
                openhab_client.start_sse_listener(
                    self._make_sse_callback(inventory_manager),
                    [item.name for item in items],
                )
                logger.info("Loaded %s semantic points into inventory", len(items))
            except Exception as e:
                logger.error("Failed to load semantic points: %s", e)

            refresh_thread = threading.Thread(
                target=self._inventory_refresh_worker,
                args=(openhab_client, inventory_manager),
                daemon=True,
            )
            refresh_thread.start()
            logger.info(
                "Inventory refresh thread started (interval: %s minutes)",
                config.inventory.refresh_minutes,
            )
            self._initialized = True

    def _make_sse_callback(self, inventory_manager):
        """Create SSE callback with closure over inventory_manager."""

        def sse_callback(item_name: str, state_obj):
            try:
                logger.debug(
                    "SSE callback triggered: item=%s, state=%s",
                    item_name,
                    state_obj.value,
                )

                # Check if state has actually changed
                item = inventory_manager.get_item(item_name)
                if item and item.state and item.state.value == state_obj.value:
                    return  # No state change, ignore

                inventory_manager.update_state_index(item_name, state_obj)

                if self.monitoring_service is not None and self.dispatcher is not None:
                    self.dispatcher.dispatch(
                        self.monitoring_service.check_triggers_async(
                            item_name, state_obj
                        )
                    )
            except Exception as e:
                logger.error("Error in SSE callback: %s", e)

        return sse_callback

    def _inventory_refresh_worker(self, openhab_client, inventory_manager):
        """Background worker to periodically refresh the inventory."""
        while True:
            try:
                time.sleep(config.inventory.refresh_minutes * 60)
                logger.info("Starting scheduled inventory refresh...")
                items = openhab_client.get_semantic_points()

                if items:
                    try:
                        inventory_manager.initialize_inventory(items)
                        item_names = [item.name for item in items]
                        openhab_client.update_sse_items(item_names)
                        logger.info(
                            "Inventory refresh completed: %s items loaded", len(items)
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

            except Exception as e:
                logger.error("Failed to refresh inventory: %s", e)
                logger.warning(
                    "Inventory refresh failed – consider manual restart if needed"
                )


runtime_manager = RuntimeManager()

# ============================================================
# Tool registrations
# ============================================================
register_discovery_tools(mcp, inventory=inventory)
register_command_tools(mcp, openhab=openhab, inventory=inventory)
register_inventory_tools(mcp, inventory=inventory)
runtime_manager.monitoring_service = register_monitoring_tools(
    mcp,
    monitoring_config=config.monitoring,
    inventory=inventory,
)


# ============================================================
# Server runner
# ============================================================
def run_server():
    """Run the MCP server."""
    try:
        runtime_manager.initialize_if_needed(openhab, inventory)
        logger.info(
            "Starting openHAB Semantic MCP Server on %s:%s",
            config.mcp.host,
            config.mcp.port,
        )
        logger.info("Connected to OpenHAB at %s", config.openhab.base_url)
        logger.info("Using MCP transport: %s", config.mcp.transport)
        mcp.run(transport=config.mcp.transport)
    except Exception as e:
        logger.error("Server error: %s", e)
        raise
    finally:
        try:
            if runtime_manager.dispatcher:
                runtime_manager.dispatcher.shutdown()
            openhab.stop_sse_listener()
            logger.info("SSE listener and dispatcher stopped on server shutdown")
        except Exception as e:
            logger.error("Error stopping SSE listener during shutdown: %s", e)


if __name__ == "__main__":
    run_server()
