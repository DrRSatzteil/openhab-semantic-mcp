# Single-stage build for simplicity
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy everything including healthcheck script
COPY pyproject.toml README.md healthcheck.py ./
COPY src/ ./src/

# Install the package and dependencies
RUN pip install .

# Test that the module can be imported
RUN python -c "import openhab_semantic_mcp; print('Module imported successfully')"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Expose the MCP server port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check - check if the MCP server is responding using Python client
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python healthcheck.py || exit 1

# Run the application using the module entry point and keep container running
CMD python -m openhab_semantic_mcp
