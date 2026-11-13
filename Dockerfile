# ==============================================================================
# Earth Pulse — Production Multi-Stage Container Definition
# NASA Space Apps Challenge 2026: Dancing with the SARs
# ==============================================================================

# Stage 1: Build the React / TypeScript WebGIS Frontend
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python & Geospatial Runtime
FROM python:3.11-slim-bookworm
LABEL maintainer="Earth Pulse Engineering Team"
LABEL description="Earth Pulse: Satellite Radar Hydrology & Explainable AI (NASA Space Apps 2026)"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/mpl_cache \
    DEMO_MODE_RESTRICTED_EXECUTION=true \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install system runtime libraries (GDAL, utilities)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source & core assets
COPY src/ ./src/
COPY models/ ./models/
COPY graphs/ ./graphs/
COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY README.md .env.example ./

# Copy compiled frontend from builder stage
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Prepare workspace & cache directories
RUN mkdir -p /app/data/metadata /app/data/runs /app/data/raw /tmp/mpl_cache && \
    chmod -R 777 /tmp/mpl_cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

