#!/usr/bin/env python3
"""
Main entry point for the openHAB Semantic MCP Server.

This module provides the command-line interface for running the MCP server.
"""

import logging
import signal
import sys
from openhab_semantic_mcp.mcp_server import run_server, openhab

# Get logger for this module
logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received signal %s, shutting down gracefully...", signum)
    
    # Stop the SSE listener
    try:
        openhab.stop_sse_listener()
        logger.info("SSE listener stopped")
    except Exception as e:
        logger.error("Error stopping SSE listener: %s", e)
    
    # Exit gracefully
    sys.exit(0)


def main():
    """Main entry point for the CLI."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    try:
        run_server()
    except Exception as e:
        logger.error("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
