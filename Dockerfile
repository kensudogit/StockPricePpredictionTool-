# Production API image (root Dockerfile for Railway / cloud builders)
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-extra.txt ./
RUN pip install -r requirements.txt \
    && pip install catboost==1.2.7 || true \
    && pip install vectorbt==0.26.2 || true \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu || true

COPY backend/ ./

EXPOSE 8000

# Cloud platforms inject $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
