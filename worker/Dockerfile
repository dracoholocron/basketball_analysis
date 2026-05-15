# GPU worker — requires nvidia-container-toolkit on the host
# Base image: PyTorch 2.7 + CUDA 12.8 for RTX 5070 (Blackwell sm_120)
FROM pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# System dependencies for OpenCV headless + libGL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libpq-dev \
    gcc \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# API service deps (for Celery + DB + Storage)
COPY api/requirements.txt /tmp/api_requirements.txt
RUN pip install --no-cache-dir -r /tmp/api_requirements.txt

# Engine deps (excluding torch — already in base image)
COPY basketball_analysis/requirements.txt /tmp/engine_requirements.txt
RUN grep -v "^torch" /tmp/engine_requirements.txt | pip install --no-cache-dir -r /dev/stdin || true

# Copy application code
COPY basketball_analysis/ /app/engine/
COPY api/ /app/api/

ENV PYTHONPATH=/app/engine:/app/api
ENV ENGINE_PATH=/app/engine

# Celery worker — GPU queue only, 1 task at a time
CMD ["celery", "-A", "app.worker.celery_app", "worker", \
     "--loglevel=info", \
     "--queues=gpu", \
     "--concurrency=1"]
