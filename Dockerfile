# ASIS Railway Ultra-Minimal Deployment
FROM python:3.11-slim

WORKDIR /app

# Copy and install only essential requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app_ultra_minimal.py .
COPY start_direct.py .

# Set environment
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Start with direct Python script
CMD ["python", "start_direct.py"]
