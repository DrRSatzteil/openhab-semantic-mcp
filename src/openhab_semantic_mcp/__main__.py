#!/usr/bin/env python3
"""
Main entry point for the openHAB Semantic MCP Server.

This module provides the command-line interface for running the MCP server.
"""

import logging
import signal
import sys
from types import FrameType
from typing import Optional

from openhab_semantic_mcp.mcp_server import (
    ServerApplication,
    bootstrap_application,
    run_server,
)

# Get logger for this module
logger = logging.getLogger(__name__)
application: Optional[ServerApplication] = None


def signal_handler(signum: int, _frame: Optional[FrameType]) -> None:
    """Handle shutdown signals gracefully."""
    logger.info("Received signal %s, shutting down gracefully...", signum)

    if application is not None:
        application.shutdown()

    sys.exit(0)


def main() -> None:
    """Main entry point for the CLI."""
    global application

    application = bootstrap_application()

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    try:
        run_server(application)
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
