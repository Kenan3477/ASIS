# ASIS Production Deployment Guide
# ==================================

# Docker Configuration
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ASIS system files
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/config

# Set environment variables
ENV PYTHONPATH=/app
ENV ASIS_CONFIG_PATH=/app/config
ENV ASIS_LOG_PATH=/app/logs
ENV ASIS_DATA_PATH=/app/data

# Expose port for API
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run ASIS
CMD ["python", "asis_production_system.py", "--production"]
