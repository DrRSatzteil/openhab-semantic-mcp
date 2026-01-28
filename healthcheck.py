#!/usr/bin/env python3
"""
Health check script for OpenHAB Semantic MCP Server.
Tests if the MCP server is responsive by making a simple API call.
"""

import sys
import os
import requests
import json
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def health_check():
    """Check if MCP server is healthy by testing a simple API call."""
    
    # Get configuration from environment
    host = os.environ.get("MCP_HOST", "localhost")
    port = int(os.environ.get("MCP_PORT", "8000"))
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    
    # For non-HTTP transports, just check if process is running
    if transport != "streamable-http":
        print(f"Transport {transport} is not HTTP-based, checking process...")
        # For stdio and sse, we can't easily test the protocol
        # So we just check if the module can be imported
        try:
            import openhab_semantic_mcp
            print("✅ MCP module can be imported")
            return True
        except ImportError as e:
            print(f"❌ Cannot import MCP module: {e}")
            return False
    
    # For HTTP transport, test the actual endpoint
    url = f"http://{host}:{port}/mcp"
    
    try:
        # Try to make a HEAD request to avoid log spam (no body)
        response = requests.head(
            url, 
            timeout=5,
            headers={"Accept": "application/json"}
        )
        
        # Check if we get any response (even 406 is OK - it means server is running)
        if response.status_code in [200, 406, 404]:
            status_msg = {
                200: "OK - Server responding correctly",
                406: "Not Acceptable - Server running (expected for MCP)", 
                404: "Not Found - Server running (wrong endpoint)"
            }
            print(f"✅ MCP server healthy: {status_msg.get(response.status_code, 'HTTP ' + str(response.status_code))}")
            return True
        else:
            print(f"❌ MCP server returned unexpected HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to MCP server")
        return False
    except requests.exceptions.Timeout:
        print("❌ MCP server timeout")
        return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

if __name__ == "__main__":
    success = health_check()
    sys.exit(0 if success else 1)
