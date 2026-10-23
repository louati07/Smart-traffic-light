FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY vision/requirements.txt /app/vision/requirements.txt
RUN pip install --no-cache-dir -r /app/vision/requirements.txt

COPY vision /app/vision
COPY data/replay /app/data/replay

ENV VISION_MODE=replay
ENV API_URL=http://api:8000/api/v1

CMD ["python", "vision/worker.py", "--mode", "replay", "--api-url", "http://api:8000/api/v1"]
