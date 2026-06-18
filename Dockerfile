# OTP Extractor backend — needs the Tesseract binary + OpenCV runtime libs,
# which is why this ships as a Docker image (Render's native runtime can't apt-install).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects $PORT; default for local `docker run`.
ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app"]
