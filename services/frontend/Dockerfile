FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy static files and pages
COPY static/ /app/static/
COPY services/frontend/pages/ /app/pages/

# Copy application code
COPY services/frontend/app/ /app/app/

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
