FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including LDAP libs for python-ldap)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared/ /app/shared/

# Install shared library
RUN pip install --no-cache-dir /app/shared/

# Copy and install service requirements
COPY services/auth/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/auth/app/ /app/app/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8011

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8011/health')" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
