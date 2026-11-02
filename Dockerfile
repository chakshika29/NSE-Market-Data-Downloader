# Use official lightweight Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, configuration, and fixtures
COPY config/ ./config/
COPY src/ ./src/
COPY fixtures/ ./fixtures/
COPY main.py .

# Create output and logs volumes/directories
RUN mkdir -p /app/output /app/logs

# Define default volume mounts for persistence
VOLUME ["/app/output", "/app/logs"]

# Set default entrypoint
ENTRYPOINT ["python", "main.py"]

# Default command: download all 4 datasets
CMD []
