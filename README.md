# openHAB Semantic MCP Server

A lightweight MCP (Model Context Protocol) server for openHAB semantic operations.

## Features

- Send commands to openHAB items based on semantic filters
- Query items by location, equipment, points, and properties
- **Dual hierarchy support**: Type-based and parent-based semantic hierarchies
- Get detailed item information from the semantic inventory
- Real-time state updates via Server-Sent Events (SSE)
- Docker deployment support
- Safety confirmations for large operations

## Installation

### Docker (Recommended)

1. **Set Environment Variables**
   
   Create a `.env` file in the project root with your openHAB credentials:
   ```bash
   cat > .env << EOF
   # openHAB Configuration (Required)
   OPENHAB_BASE_URL=https://your-openhab-instance.org
   OPENHAB_API_TOKEN=your_api_token_here
   
   # MCP Server Configuration
   MCP_HOST=0.0.0.0
   MCP_PORT=8000
   MCP_TRANSPORT=streamable-http
   LOG_LEVEL=INFO
   
   # Inventory Configuration
   INVENTORY_REFRESH_MINUTES=60
   EOF
   ```

2. **Build and Run with Docker Compose**
   
   ```bash
   docker-compose up -d
   ```
   
   The server will start on port 8000.

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
   # Edit the .env file with your openHAB configuration
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
MCP_PORT=8000
MCP_TRANSPORT=streamable-http
LOG_LEVEL=INFO
INVENTORY_REFRESH_MINUTES=60
```

**Required:**
- `OPENHAB_BASE_URL`: URL of your openHAB instance
- `OPENHAB_API_TOKEN`: API token for authentication

**Optional:**
- `MCP_HOST`: Host to bind the MCP server (default: 0.0.0.0)
- `MCP_PORT`: Port for the MCP server (default: 8000)
- `MCP_TRANSPORT`: Transport mode for MCP communication (default: streamable-http)
  - `streamable-http`: HTTP-based transport (recommended for Docker/containers)
  - `stdio`: Standard input/output transport (for local development only - **not compatible with Docker**)
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

## Semantic Hierarchies

The server supports **dual hierarchy systems** for powerful semantic queries:

### Type-Based Hierarchies
Uses semantic naming conventions with underscore separators:
- `Lighting_CeilingLight_Downlight` → indexed under `Lighting`, `Lighting_CeilingLight`, and `Lighting_CeilingLight_Downlight`
- `Indoor_Room_DiningRoom` → indexed under `Indoor`, `Indoor_Room`, and `Indoor_Room_DiningRoom`

### Parent-Based Hierarchies  
Uses openHAB `isPartOf` semantic relationships:
- Equipment can have parent equipment relationships
- Locations inherit from parent locations
- Items without direct location inherit location from parent equipment

### Query Examples

```python
# Type-based queries
get_items(location="Indoor")           # All indoor items
get_items(equipment="Lighting")       # All lighting equipment
get_items(equipment="Lighting_CeilingLight")  # All ceiling lights

# Parent-based queries (with recursive location inheritance)
get_items(location="Indoor_Room_DiningRoom")  # Items in dining room (including nested equipment)
get_items(equipment="LightSource_AccentLight") # All accent lights (inherited from parent equipment)

# Combined queries
get_items(location="Indoor", equipment="Lighting")  # All indoor lighting
```

## Testing

The project includes comprehensive tests for the dual hierarchy system:

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=openhab_semantic_mcp
```

Test coverage includes:
- DTO models and relationships
- Inventory indexing with dual hierarchies
- openHAB client semantic parsing
- Hierarchical query functionality
