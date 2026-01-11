FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    curl \
    git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Install mcp-atlassian via pip (CORRECT METHOD) ----
RUN pip install --no-cache-dir mcp-atlassian

# App code
COPY src ./src
COPY config ./config

CMD ["python", "src/main.py"]