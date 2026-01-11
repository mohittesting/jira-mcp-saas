FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    curl \
    git \
    nodejs \
    npm \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- MCP Atlassian (CORRECT PATH) ----
RUN git clone https://github.com/sooperset/mcp-atlassian.git /mcp-atlassian \
 && cd /mcp-atlassian/packages/server-atlassian \
 && npm install

# App code
COPY src ./src
COPY config ./config

CMD ["python", "src/main.py"]
