# services/ai/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Copy and install service requirements
COPY services/ai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/ai/app /app/app

# Copy AI module for agent/tool logic
COPY ai/ /app/ai/

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
