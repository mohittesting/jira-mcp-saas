FROM python:3.11-slim

# Install Node.js and npm (required for npx and MCP server)
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN node --version && npm --version

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Pre-install the MCP Atlassian package globally (optional but recommended)
RUN npm install -g @modelcontextprotocol/server-atlassian

# Railway will set environment variables
CMD ["python", "main.py"]