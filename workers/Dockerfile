FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libpq-dev \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared/ /app/shared/

# Install shared library
RUN pip install --no-cache-dir /app/shared/

# Copy and install worker requirements
COPY workers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY workers/ /app/

# Set Python path
ENV PYTHONPATH=/app

# Default command - can be overridden for beat
CMD ["celery", "-A", "celery_app", "worker", "-l", "info", "-Q", "device_tasks,celery", "-c", "10"]
