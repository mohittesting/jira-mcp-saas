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

# Copy everything from your project
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install the MCP Atlassian package globally
RUN npm install -g @modelcontextprotocol/server-atlassian

# Run the main.py from src directory
CMD ["python", "src/main.py"]