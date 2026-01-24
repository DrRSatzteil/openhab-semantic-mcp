# OpenHAB Semantic MCP Server

A lightweight MCP (Model Context Protocol) server for OpenHAB semantic operations.

## Features

- Send commands to OpenHAB items based on semantic filters
- Query items by location, equipment, points, and properties
- Get detailed item information from the semantic inventory
- Real-time state updates via Server-Sent Events (SSE)
- Docker deployment support
- Safety confirmations for large operations

## Installation

### Docker (Recommended)

1. **Set Environment Variables**
   
   Create a `.env` file in the project root with your OpenHAB credentials:
   ```bash
   cat > .env << EOF
   OPENHAB_BASE_URL=https://your-openhab-instance.org
   OPENHAB_API_TOKEN=your_api_token_here
   MCP_HOST=0.0.0.0
   MCP_PORT=8001
   LOG_LEVEL=INFO
   EOF
   ```

2. **Build and Run with Docker Compose**
   
   ```bash
   docker-compose up -d
   ```
   
   The server will start on port 8001.

3. **Check Logs**
   
   ```bash
   docker-compose logs -f openhab-semantic-mcp
   ```

4. **Stop the Service**
   
   ```bash
   docker-compose down
   ```

### Local Development

1. **Clone and set up environment**
   ```bash
   git clone <repository-url>
   cd openhab-semantic-mcp
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .
   ```

2. **Configure environment**
   ```bash
   cp src/openhab_semantic_mcp/.env.example .env
   # Edit the .env file with your OpenHAB configuration
   ```

3. **Run the server**
   ```bash
   python -m openhab_semantic_mcp
   ```


## Configuration

Configure the server using environment variables in a `.env` file:

```bash
OPENHAB_BASE_URL=https://your-openhab-instance.org
OPENHAB_API_TOKEN=your_api_token_here
MCP_HOST=0.0.0.0
MCP_PORT=8001
MCP_TRANSPORT=streamable-http
LOG_LEVEL=INFO
INVENTORY_REFRESH_MINUTES=60
```

**Required:**
- `OPENHAB_BASE_URL`: URL of your OpenHAB instance
- `OPENHAB_API_TOKEN`: API token for authentication

**Optional:**
- `MCP_HOST`: Host to bind the MCP server (default: 0.0.0.0)
- `MCP_PORT`: Port for the MCP server (default: 8001)
- `MCP_TRANSPORT`: Transport mode for MCP communication (default: streamable-http)
  - `streamable-http`: HTTP-based transport (recommended for Docker/containers)
  - `stdio`: Standard input/output transport (for local development)
  - `sse`: Server-Sent Events transport
- `LOG_LEVEL`: Logging level (default: INFO)
- `INVENTORY_REFRESH_MINUTES`: Interval for refreshing the semantic inventory (default: 60)


## Available Tools

The MCP server provides these semantic tools:

- **get_available_semantic_entities**: Discover all semantic entities (locations, equipment, points, properties)
- **get_items**: Query items with semantic filters
- **get_item_details**: Get detailed information about a specific item
- **send_command_to_entities**: Send commands to items based on semantic filters
- **update_entities_state**: Update states of items based on semantic filters


## Security

- Never commit `.env` files to version control
- Use strong API tokens for OpenHAB authentication
- The Docker container runs as a non-root user for security
- Consider using Docker secrets or Kubernetes secrets for production deployments

## License

[Add your license information here]
