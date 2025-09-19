# ASIS Railway Minimal Deployment
FROM python:3.11-slim

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y gcc curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app_minimal.py .
COPY . .

# Set environment
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Start minimal app
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "app_minimal:app"]
