# Earth Pulse SAR — Production Deployment & Runtime Operations Guide
**NASA Space Apps Challenge 2026: Dancing with the SARs**  
**Role:** DevOps Engineer & Cloud Deployment Architect

---

## 1. System Requirements & Hardware Prerequisites

| Requirement | Minimum | Recommended Production |
| :--- | :--- | :--- |
| **Operating System** | Linux (Ubuntu 22.04 LTS / Debian 12) | Linux (Ubuntu 22.04+ / RHEL 9) |
| **CPU Architecture** | x86_64 (4 cores) | x86_64 (8+ cores) |
| **Memory (RAM)** | 8 GB | 16 GB - 32 GB (ESA SNAP JVM heap) |
| **Local Disk Space** | 20 GB free | 100 GB+ SSD (raw Sentinel-1 granules $\approx 1\text{ GB}$ each) |
| **Network** | Outbound HTTPS (443) | High-speed link for ASF DAAC downloads |

---

## 2. Core Software Prerequisites

### 2.1 Geospatial C-Libraries & GDAL
Earth Pulse utilizes GDAL for spatial warping, subsetting, and GeoTIFF generation:
```bash
sudo apt-get update && sudo apt-get install -y \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    libspatialindex-dev
```

### 2.2 ESA SNAP (Sentinel Application Platform)
ESA SNAP provides the radar terrain correction engine (`gpt` CLI):
1. Download ESA SNAP 10.x for Linux from the [ESA Step Portal](https://step.esa.int/main/download/snap-download/).
2. Run headless installation:
   ```bash
   bash esa-snap_sentinel_unix_10_0_0.sh -q -dir /opt/snap
   ```
3. Verify that `gpt` is executable:
   ```bash
   /opt/snap/bin/gpt -h
   ```
4. Set the environment variable:
   ```bash
   export SNAP_GPT_PATH="/opt/snap/bin/gpt"
   ```

---

## 3. Python Environment Setup

Clone the repository and install required packages:
```bash
cd EarthPulse-SAR
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Environment Variables & Safe Configuration

Copy the provided `.env.example` template:
```bash
cp .env.example .env
```

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `EARTH_PULSE_DATA_DIR` | `<repo_root>/data` | Directory where processed rasters, runs, and metadata are persisted. Point to an external high-capacity drive or mounted volume in production. |
| `SNAP_GPT_PATH` | `/home/orr/esa-snap/bin/gpt` | Absolute path to the ESA SNAP `gpt` executable. |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated list of allowed CORS origins for frontend integration. |
| `DEMO_MODE_RESTRICTED_EXECUTION` | `true` | **CRITICAL FAIL-SAFE SAFETY GATE.** Defaults to `true` when unset. When `true`, all new job creation (`POST /api/v1/analysis-requests`) is rejected with `HTTP 403 Forbidden`, preventing unauthenticated compute exhaustion. Precomputed scientific runs are served via GET endpoints. Set to `false` only in authenticated or private enterprise environments. |
| `EARTHDATA_USERNAME` | *empty* | NASA Earthdata username for automated Sentinel-1 downloads via ASF DAAC. |
| `EARTHDATA_PASSWORD` | *empty* | NASA Earthdata user password. |

---

## 5. Running the Application

### 5.1 Local Development / Testing
```bash
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5.2 Production ASGI Deployment (Gunicorn + Uvicorn Workers)
```bash
gunicorn src.backend.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
```

### 5.3 Frontend Application Development & Build
The frontend is a React 18 + TypeScript + Vite single-page application located in `frontend/`.

```bash
cd frontend
npm install

# Start development server on port 5173 with automatic backend proxy to :8000
npm run dev

# Production build (creates optimized bundle in frontend/dist/)
npm run build
```

### 5.4 Health Check Verification
Verify the backend status:
```bash
curl -f http://localhost:8000/api/v1/health
# Response: {"status":"healthy","version":"1.0.0"}
```

---

## 6. Critical Public Exposure & Compute Safety

> [!WARNING]
> Dynamic Sentinel-1 processing involves downloading $\approx 1\text{ GB}$ archives and running multi-stage ESA SNAP Range Doppler Terrain Correction requiring up to 12 GB RAM and several minutes of continuous CPU computation per scene.
>
> **Do not expose `POST /api/v1/analysis-requests` unrestricted to the public internet with `DEMO_MODE_RESTRICTED_EXECUTION=false`.**
>
> In public web deployments:
> 1. Keep `DEMO_MODE_RESTRICTED_EXECUTION=true` (the default) so public callers cannot trigger compute exhaustion. All precomputed historical and live demonstration runs are served safely and instantly via GET endpoints (`GET /api/v1/runs`, `GET /api/v1/runs/{run_id}/summary`, `GET /api/v1/runs/{run_id}/tiles/{z}/{x}/{y}.png`, etc.).
> 2. For custom AOIs or on-demand processing, deploy behind an authenticating proxy (OAuth2 / JWT) enforcing per-user quotas and concurrency limits, and only enable `DEMO_MODE_RESTRICTED_EXECUTION=false` in that authenticated environment.

