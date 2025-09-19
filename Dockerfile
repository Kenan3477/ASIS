# ASIS Railway Production Deployment
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
    bash \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ASIS system files
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/config

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8000

# Expose port (Railway will set PORT dynamically)
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Use startup script
CMD ["bash", "start.sh"]
