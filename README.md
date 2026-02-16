# openHAB Semantic MCP Server

A lightweight MCP (Model Context Protocol) server for openHAB semantic operations.

## Features

- Send commands to openHAB items based on semantic filters
- Query items by location, equipment, points, and properties
- **Command validation**: Uses openHAB Command Description metadata to prevent invalid commands
- **State validation**: Uses openHAB State Description metadata to prevent invalid state updates
- **Recursive equipment relationships**: Parent-child equipment chains for device grouping
- **Dual hierarchy support**: Type-based and parent-based semantic hierarchies
- Get detailed item information from the semantic inventory
- Real-time state updates via Server-Sent Events (SSE)
- **Monitoring Tasks**: Create time-based monitoring tasks with webhook triggers
- **Dynamic Timezone Support**: Automatic timezone handling with LLM-aware tool descriptions
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
   
   # Monitoring Configuration (Required)
   MONITORING_WEBHOOK_URL=https://your-webhook-endpoint.org/webhook
   MONITORING_WEBHOOK_AUTH_HEADER=Authorization: Bearer your_webhook_token
   MONITORING_TIMEZONE=Europe/Berlin
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

# Monitoring Configuration (Required)
MONITORING_WEBHOOK_URL=https://your-webhook-endpoint.org/webhook
MONITORING_WEBHOOK_AUTH_HEADER=Authorization: Bearer your_webhook_token
MONITORING_TIMEZONE=Europe/Berlin

# Optional Monitoring Settings
MONITORING_STORAGE_TYPE=memory
MONITORING_CLEANUP_INTERVAL_MINUTES=60
MONITORING_RETAIN_COMPLETED_DAYS=7
MONITORING_RETAIN_CANCELLED_DAYS=3
MONITORING_RETAIN_ERROR_DAYS=7
MONITORING_ENABLE_AUTO_CLEANUP=true
```

**Required:**
- `OPENHAB_BASE_URL`: URL of your openHAB instance
- `OPENHAB_API_TOKEN`: API token for authentication
- `MONITORING_WEBHOOK_URL`: Webhook endpoint for monitoring task notifications
- `MONITORING_TIMEZONE`: Timezone for monitoring tasks (e.g., Europe/Berlin, America/New_York)

**Optional:**
- `MCP_HOST`: Host to bind the MCP server (default: 0.0.0.0)
- `MCP_PORT`: Port for the MCP server (default: 8000)
- `MCP_TRANSPORT`: Transport mode for MCP communication (default: streamable-http)
  - `streamable-http`: HTTP-based transport (recommended for Docker/containers)
  - `stdio`: Standard input/output transport (for local development only - **not compatible with Docker**)
  - `sse`: Server-Sent Events transport
- `LOG_LEVEL`: Logging level (default: INFO)
- `INVENTORY_REFRESH_MINUTES`: Interval for refreshing the semantic inventory (default: 60)
- `MONITORING_WEBHOOK_AUTH_HEADER`: Authorization header for webhook requests (format: `Key: Value`)
- `MONITORING_STORAGE_TYPE`: Storage backend type: `memory`, `file`, or `caldav` (default: memory)
- `MONITORING_STORAGE_CONFIG`: Backend-specific configuration as JSON string (see [Storage Backends](#storage-backends))
- `MONITORING_CLEANUP_INTERVAL_MINUTES`: Cleanup interval in minutes (default: 60)
- `MONITORING_RETAIN_COMPLETED_DAYS`: Days to retain completed tasks (default: 7)
- `MONITORING_RETAIN_CANCELLED_DAYS`: Days to retain cancelled tasks (default: 3)
- `MONITORING_RETAIN_ERROR_DAYS`: Days to retain error tasks (default: 7)
- `MONITORING_ENABLE_AUTO_CLEANUP`: Enable automatic cleanup (default: true)


## Available Tools

The MCP server provides these semantic tools:

### Core Semantic Tools
- **get_available_semantic_entities**: Discover all semantic entities (locations, equipment, points, properties)
- **get_items**: Query items with semantic filters
- **send_command_to_entities**: Send commands to items based on semantic filters
- **update_entities_state**: Update states of items based on semantic filters

### Monitoring Tools
- **create_monitoring_task**: Create time-based monitoring tasks with webhook triggers
- **get_monitoring_task_status**: Get status and details of a monitoring task
- **cancel_monitoring_task**: Cancel an active monitoring task

## Command & State Validation

The server automatically validates commands and state updates using openHAB's metadata:

### Command Validation
- **Command Description**: Uses `commandDescription.commandOptions` from openHAB
- **Prevention**: Blocks invalid commands before sending to openHAB
- **Feedback**: Shows valid commands from command metadata

### State Validation  
- **State Description**: Uses `stateDescription.options` from openHAB
- **Prevention**: Blocks invalid state updates
- **Feedback**: Shows valid states from state metadata

### Example Error Response
```json
{
  "success": false,
  "error": "Command 'BLINK' not allowed. Allowed commands: ['ON', 'OFF', 'AUTO']",
  "allowed_commands": ["ON", "OFF", "AUTO"]
}
```

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
get_items(location="Indoor", equipment="LightSource")  # All indoor lighting
get_items(location="Indoor_Floor_GroundFloor", equipment="LightSource", point="Control_Switch", property="Light")  # All ground floor light switches
get_items(point="Measurement", property="Humidity")  # All humidity measurements
get_items(equipment="HVAC", point="Control")  # All controls related to HVAC
```

## Monitoring Tasks

The server supports advanced monitoring capabilities with time-based task scheduling:

### Features
- **Time-based scheduling**: Create tasks that monitor items during specific time windows
- **Webhook notifications**: Automatic webhook triggers when monitoring conditions are met
- **Dynamic timezone support**: Automatic timezone handling with LLM-aware descriptions
- **Multiple storage backends**: Memory, file, or CalDAV storage for task persistence
- **Automatic cleanup**: Configurable retention policies for completed tasks

### Creating Monitoring Tasks

```python
# Monitor a light switch for 10 minutes
create_monitoring_task(
    mode="time_window",
    start_time="2026-02-10T14:48:00",  # Interpreted in configured timezone
    end_time="2026-02-10T14:58:00",
    filters={
        "location": "Indoor_Room_LivingRoom",
        "equipment": "LightSource_FloorLamp", 
        "point": "Control_Switch"
    }
)

# One-shot task - triggers once when condition is met
create_monitoring_task(
    mode="one_shot",
    end_time="2026-02-10T23:59:00",
    filters={"point": "Status_OpenState", "state": {"kind": "exact", "states": ["OPEN"]}}
)
```

### Timezone Handling

All times are automatically interpreted in the configured timezone:

```bash
# Configure timezone (required)
MONITORING_TIMEZONE=Europe/Berlin    # European time
MONITORING_TIMEZONE=America/New_York  # US Eastern time  
MONITORING_TIMEZONE=Asia/Tokyo        # Japan time
```

The LLM automatically receives timezone information in tool descriptions, ensuring correct time interpretation.

### Storage Backends

Select the backend with `MONITORING_STORAGE_TYPE` and configure it via `MONITORING_STORAGE_CONFIG` (a JSON string keyed by backend name):

**Memory** (default) - In-memory storage, data lost on restart:
```bash
MONITORING_STORAGE_TYPE=memory
MONITORING_STORAGE_CONFIG='{"memory": {}}'
```

**File** - JSON file persistence:
```bash
MONITORING_STORAGE_TYPE=file
MONITORING_STORAGE_CONFIG='{"file": {"file_path": "monitoring_tasks.json"}}'
```

**CalDAV** - Calendar-based storage with background sync:
```bash
MONITORING_STORAGE_TYPE=caldav
MONITORING_STORAGE_CONFIG='{"caldav": {"url": "https://caldav.example.org/remote.php/dav/principals/users/user/", "username": "user", "password": "pass", "calendar_name": "monitoring", "sync_interval": 300}}'
```

### Webhook Payload

When a monitoring task triggers, it sends a webhook with detailed event information:

```json
{
  "task_id": "monitor_abc123",
  "mode": "time_window",
  "triggered_at": "2026-02-10T14:52:30+01:00",
  "trigger_count": 1,
  "item": {
    "name": "floorlamp_livingroom_toggle",
    "state": "ON",
    "display_state": "An",
    "unit": null
  },
  "task_config": {
    "filters": {
      "location": "Indoor_Room_LivingRoom",
      "equipment": "LightSource_FloorLamp"
    },
    "refinement": null,
    "last_state_transition": "2026-02-10T14:48:00+01:00"
  },
  "time_window": {
    "start_time": "2026-02-10T14:48:00+01:00",
    "end_time": "2026-02-10T14:58:00+01:00"
  }
}
```

## Testing

```bash
# Install test dependencies
pip install -e ".[test]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=openhab_semantic_mcp --cov-report=html
```

Test coverage includes:
- DTO models and relationships
- Inventory indexing with dual hierarchies
- openHAB client semantic parsing
- Monitoring system (service layer, trigger evaluation, webhook management)
- CalDAV backend (connection, event mapping, calendar synchronization)
- Storage backends (memory, file, CalDAV)
