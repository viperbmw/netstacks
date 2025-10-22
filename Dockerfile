FROM python:3.9-slim

WORKDIR /app

# Install system dependencies required for python-ldap and timezone support
RUN apt-get update && apt-get install -y \
    gcc \
    libldap2-dev \
    libsasl2-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /data && chmod 777 /data

# Expose port 8088
EXPOSE 8089

# Set environment variables
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV DB_FILE=/data/netstackspro.db

# Run the application
CMD ["python", "app.py"]
