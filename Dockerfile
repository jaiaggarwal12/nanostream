FROM python:3.11-slim

# System dependencies including ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create persistent output directories
RUN mkdir -p uploads hls_output nanostream_results dataset

EXPOSE 8000

# Use $PORT env var if provided (Render sets this), fallback to 8000
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
