FROM python:3.12-slim

# Analysis uses Gemini via google-genai (pure Python) — no Node/CLI needed.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DB_PATH=/data/journal.db
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.main"]
