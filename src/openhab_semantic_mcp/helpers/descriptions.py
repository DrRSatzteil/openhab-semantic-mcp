"""Common field descriptions used across MCP tools to ensure consistency."""

REFINEMENT_DESCRIPTION = (
    "ONLY use for ambiguity! "
    "List of item names for additional filtering. "
    "Combined with semantic filters. "
    "Normal semantic filters take priority. "
    "IMPORTANT: Only use item names that were returned by previous get_items() calls. "
    "DO NOT invent or guess item names - this will cause errors."
)

FILTERS_DESCRIPTION = "Standard semantic search filters"
FILTERS_DESCRIPTION_MONITORING = "Standard semantic search filters for event detection"
