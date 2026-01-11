FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    curl \
    git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (modern Python package installer)
RUN pip install --no-cache-dir uv

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Install mcp-atlassian via uv ----
RUN uv tool install mcp-atlassian

# Add uv tools to PATH
ENV PATH="/root/.local/bin:${PATH}"

# App code
COPY src ./src
COPY config ./config

CMD ["python", "src/main.py"]