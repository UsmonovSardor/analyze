FROM python:3.12-slim

# Node.js is required by claude-agent-sdk (it drives the Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DB_PATH=/data/journal.db
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.main"]
