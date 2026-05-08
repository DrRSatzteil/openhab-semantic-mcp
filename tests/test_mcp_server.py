"""Tests for MCP server bootstrap and lifecycle management."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from openhab_semantic_mcp.config import load_config


def test_importing_mcp_server_has_no_startup_side_effects(monkeypatch):
    """Importing the module should not load config or start threads."""
    sys.modules.pop("openhab_semantic_mcp.mcp_server", None)

    calls = {"load_config": 0, "thread_start": 0}
    config_module = importlib.import_module("openhab_semantic_mcp.config")

    def fake_load_config(*args, **kwargs):
        calls["load_config"] += 1
        raise AssertionError("load_config should not run during import")

    def fake_thread_start(self):
        calls["thread_start"] += 1
        raise AssertionError("threads should not start during import")

    monkeypatch.setattr(config_module, "load_config", fake_load_config)
    monkeypatch.setattr("threading.Thread.start", fake_thread_start)

    module = importlib.import_module("openhab_semantic_mcp.mcp_server")

    assert module.bootstrap_application is not None
    assert calls == {"load_config": 0, "thread_start": 0}


def test_bootstrap_application_wires_dependencies(monkeypatch):
    """Bootstrap should create and connect all core services explicitly."""
    module = importlib.import_module("openhab_semantic_mcp.mcp_server")
    env_file = Path("/tmp/test.env")
    calls = {
        "load_config": None,
        "timezone": None,
        "discovery": None,
        "commands": None,
        "inventory": None,
        "monitoring": None,
    }

    config = SimpleNamespace(
        log_level="INFO",
        openhab=SimpleNamespace(base_url="http://openhab", api_token="token"),
        mcp=SimpleNamespace(host="127.0.0.1", port=8080, transport="stdio"),
        monitoring=SimpleNamespace(storage_type="memory", timezone="UTC"),
        inventory=SimpleNamespace(refresh_minutes=15),
    )

    class FakeFastMCP:
        def __init__(self, name, host, port, log_level, json_response):
            self.name = name
            self.host = host
            self.port = port
            self.log_level = log_level
            self.json_response = json_response

        def run(self, transport):
            self.transport = transport

    class FakeOpenHAB:
        def __init__(self, base_url, api_token=None):
            self.base_url = base_url
            self.api_token = api_token

        def stop_sse_listener(self):
            return None

    class FakeInventory:
        pass

    class FakeRuntimeManager:
        def __init__(self):
            self.monitoring_service = None

        def initialize_if_needed(self, openhab, inventory, refresh_minutes):
            self.initialize_args = (openhab, inventory, refresh_minutes)

        def shutdown(self):
            self.shutdown_called = True

    class FakeMonitoringService:
        def __init__(self):
            self.shutdown_count = 0

        def shutdown(self):
            self.shutdown_count += 1

    monitoring_service = FakeMonitoringService()

    def fake_load_config(*, env_file=None):
        calls["load_config"] = env_file
        return config

    def fake_set_default_timezone(timezone):
        calls["timezone"] = timezone

    def fake_register_discovery_tools(mcp, *, inventory):
        calls["discovery"] = (mcp, inventory)

    def fake_register_command_tools(mcp, *, openhab, inventory):
        calls["commands"] = (mcp, openhab, inventory)

    def fake_register_inventory_tools(mcp, *, inventory):
        calls["inventory"] = (mcp, inventory)

    def fake_register_monitoring_tools(mcp, *, monitoring_config, inventory):
        calls["monitoring"] = (mcp, monitoring_config, inventory)
        return monitoring_service

    monkeypatch.setattr(module, "load_config", fake_load_config)
    monkeypatch.setattr(module, "set_default_timezone", fake_set_default_timezone)
    monkeypatch.setattr(module, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(module, "OpenHAB", FakeOpenHAB)
    monkeypatch.setattr(module, "Inventory", FakeInventory)
    monkeypatch.setattr(module, "RuntimeManager", FakeRuntimeManager)
    monkeypatch.setattr(
        module, "register_discovery_tools", fake_register_discovery_tools
    )
    monkeypatch.setattr(module, "register_command_tools", fake_register_command_tools)
    monkeypatch.setattr(
        module, "register_inventory_tools", fake_register_inventory_tools
    )
    monkeypatch.setattr(
        module, "register_monitoring_tools", fake_register_monitoring_tools
    )

    app = module.bootstrap_application(env_file=env_file)

    assert calls["load_config"] == env_file
    assert calls["timezone"] == "UTC"
    assert isinstance(app.mcp, FakeFastMCP)
    assert isinstance(app.openhab, FakeOpenHAB)
    assert isinstance(app.inventory, FakeInventory)
    assert isinstance(app.runtime_manager, FakeRuntimeManager)
    assert app.monitoring_service is monitoring_service
    assert app.runtime_manager.monitoring_service is monitoring_service
    assert calls["discovery"] == (app.mcp, app.inventory)
    assert calls["commands"] == (app.mcp, app.openhab, app.inventory)
    assert calls["inventory"] == (app.mcp, app.inventory)
    assert calls["monitoring"] == (app.mcp, config.monitoring, app.inventory)


def test_load_config_reads_explicit_env_file(tmp_path, monkeypatch):
    """load_config should honor an explicit env file path."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENHAB_BASE_URL=http://env-openhab",
                "MCP_PORT=9001",
                "MONITORING_WEBHOOK_URL=https://example.test/webhook",
            ]
        )
    )

    for env_name in (
        "OPENHAB_BASE_URL",
        "MCP_PORT",
        "MONITORING_WEBHOOK_URL",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = load_config(env_file=env_file)

    assert config.openhab.base_url == "http://env-openhab"
    assert config.mcp.port == 9001
    assert config.monitoring.webhook_url == "https://example.test/webhook"


def test_run_server_uses_explicit_application():
    """run_server should operate on the provided application instance."""
    module = importlib.import_module("openhab_semantic_mcp.mcp_server")
    calls = {"initialize": 0, "run": [], "shutdown": 0}

    class FakeMCP:
        def run(self, transport):
            calls["run"].append(transport)

    class FakeApp:
        def __init__(self):
            self.config = SimpleNamespace(
                mcp=SimpleNamespace(host="127.0.0.1", port=8080, transport="stdio"),
                openhab=SimpleNamespace(base_url="http://openhab"),
            )
            self.mcp = FakeMCP()

        def initialize(self):
            calls["initialize"] += 1

        def shutdown(self):
            calls["shutdown"] += 1

    app = FakeApp()

    result = module.run_server(app)

    assert result is app
    assert calls["initialize"] == 1
    assert calls["run"] == ["stdio"]
    assert calls["shutdown"] == 1


def test_server_application_shutdown_is_idempotent():
    """Shutdown should only stop managed services once."""
    module = importlib.import_module("openhab_semantic_mcp.mcp_server")

    class FakeOpenHAB:
        def __init__(self):
            self.stop_count = 0

        def stop_sse_listener(self):
            self.stop_count += 1

    class FakeRuntimeManager:
        def __init__(self):
            self.shutdown_count = 0

        def shutdown(self):
            self.shutdown_count += 1

    class FakeMonitoringService:
        def __init__(self):
            self.shutdown_count = 0

        def shutdown(self):
            self.shutdown_count += 1

    openhab = FakeOpenHAB()
    runtime_manager = FakeRuntimeManager()
    monitoring_service = FakeMonitoringService()
    app = module.ServerApplication(
        config=SimpleNamespace(inventory=SimpleNamespace(refresh_minutes=1)),
        mcp=SimpleNamespace(),
        openhab=openhab,
        inventory=SimpleNamespace(),
        runtime_manager=runtime_manager,
        monitoring_service=monitoring_service,
    )

    app.shutdown()
    app.shutdown()

    assert openhab.stop_count == 1
    assert runtime_manager.shutdown_count == 1
    assert monitoring_service.shutdown_count == 1
