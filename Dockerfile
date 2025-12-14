FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app

# Create runtime directories
RUN mkdir -p uploads outputs

EXPOSE 5000

# Run with gunicorn for a production-ready worker
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]
