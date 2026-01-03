FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY services/ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/ingestion/app/ ./app/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8162/health'); exit(0 if r.status_code == 200 else 1)"

# Expose ports
# 162 - SNMP trap receiver (UDP)
# 8162 - Health check HTTP
# Note: This service also consumes from external Kafka/Redis if configured
EXPOSE 162/udp
EXPOSE 8162

# Run the service
CMD ["python", "-m", "app.main"]
