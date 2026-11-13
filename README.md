# Earth Pulse — Dancing with the SARs
### NASA Space Apps Challenge 2026: Satellite Radar Hydrology & Explainable AI

[![Backend Tests](https://img.shields.io/badge/pytest-558%20passed-success?style=flat-square&logo=pytest)](./tests/)
[![Frontend Tests](https://img.shields.io/badge/npm%20test-22%20passed-success?style=flat-square&logo=node.js)](./frontend/scripts/run-tests.mjs)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178C6?style=flat-square&logo=typescript)](https://www.typescriptlang.org/)

**Study Area:** Jamuna River braided reach (Kazipur / Sirajganj, Bangladesh)  
**Primary Sensor:** Copernicus Sentinel-1 C-band SAR (IW GRDH VV/VH)  
**Architecture:** FastAPI REST API + React/TypeScript (Vite + Leaflet) + GDAL + Scikit-learn Random Forest + Saabas Tree-Path XAI

---

## 1. Overview & Capabilities

Earth Pulse is an end-to-end satellite radar intelligence web application and scientific processing pipeline designed for the NASA Space Apps Challenge 2026 (*Dancing with the SARs*). It monitors extreme monsoon flooding, riverbank migration, and channel morphodynamics along the dynamic braided Jamuna River using all-weather Copernicus Sentinel-1 Synthetic Aperture Radar (SAR) backscatter.

The application features a complete multi-page WebGIS frontend with six dedicated views:
1. **Mission Dashboard (`/`):** Real-time hydrological KPIs, campaign comparison cards, and river reach overview.
2. **Satellite Map Explorer (`/explorer`):** Interactive WebGIS with an authentic OpenStreetMap raster basemap (zero API keys/watermarks), 6 scientific layer selectors, opacity slider, AOI zoom focus, and live coordinate readout.
3. **New Satellite Analysis (`/new-analysis`):** Interactive WebGIS workspace for custom Area of Interest (AOI) drawing (bounding box, polygon, or Kazipur reach shortcut), observation date selection, real Sentinel-1 catalogue search via NASA ASF DAAC, compatible orbit-track scene pairing, and job execution management with public demo protection.
4. **Flood Comparison (`/comparison`):** Dual-epoch synchronized side-by-side comparison (T1 Baseline vs T2 Observation), pixel-level 6-class flood transition accounting, and riverbank morphodynamics gate status.
5. **Explainable AI (`/explainable-ai`):** Saabas tree-path feature attribution decomposition ($f(x) = \text{base} + \sum \phi_i$) for the 40-tree Random Forest classifier, feature importance ranking, and tree additivity verification.
6. **Science & Methodology (`/science`):** Detailed documentation of the 6 scientific pillars, microwave physics, ESA SNAP calibration equations, and data provider attributions.

### Verified operating scope

- The two packaged Jamuna campaigns are archived processed analyses. Their measurements are loaded by run ID and remain available as demonstrations.
- The AOI drawing and ASF catalogue interfaces accept user-selected geometry and dates, but the processing backend currently enforces the configured Jamuna study boundary and a 200 km² maximum AOI. Catalogue search success does not imply that a request is processable.
- The current date form selects one inclusive search range and lets the user choose a returned compatible pair. Four independent baseline/comparison window controls are not implemented.
- New processing is disabled by default (`DEMO_MODE_RESTRICTED_EXECUTION=true`). The local environment can start the API and frontend, and the packaged run summary and visual manifest are served successfully. A new AOI/new-date download-to-GeoTIFF run has not been verified in this environment; the documented private path requires Earthdata access and ESA SNAP (`gpt`).
- New geographic regions require additional processing support, including location-appropriate projection and DEM coverage, area computation, and riverbank reference geometry. The frozen RF model registry is scoped to `jamuna_sirajganj`.

These constraints describe the current implementation and should not be read as a claim of global processing coverage.

---

## 2. Verified Demonstration Data

Earth Pulse ships with two verified scientific demonstration campaigns packaged in the portable demonstration archive (`EARTH_PULSE_PORTABLE_DEMO_DATA.zip`):

| Campaign | Period | Net Water Change | Verified Transects | Status |
|:---|:---:|:---:|:---:|:---:|
| **2024 Historical Monsoon** | 2024-06-10 → 2024-07-16 | **+5.8432 km²** | 36 legacy | ✅ VERIFIED |
| **2025 Live SAR Run** | 2025-01-12 → 2025-01-24 | **+1.0440 km²** | 35 / 36 qualified | ✅ VERIFIED |

**Protected scientific invariants:**
- Frozen Random Forest model (`models/phase7a/phase7a_random_forest_model.joblib`): `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`
- Canonical SNAP graph (`graphs/s1_grd_calibration_terrain_correction.xml`): `c239c2691ebcf45b778e171553c1656f9ce4d4a1dded160d929fa8e73cf316a0`
- Demonstration data archive (`EARTH_PULSE_PORTABLE_DEMO_DATA.zip`): `032a9b3e605d734aa39ed1e00c36a7adf52520945f560a4a95616e7040903462` (16,991,726 bytes)
- Release Manifest: [`docs/RELEASE_MANIFEST.json`](./docs/RELEASE_MANIFEST.json)

---

## 3. Public Demo Mode vs. Private Live Processing

### Public Demo Mode (Default — `DEMO_MODE_RESTRICTED_EXECUTION=true`)
- Safely runs out-of-the-box without NASA Earthdata credentials, ESA SNAP installation, or multi-gigabyte SAR downloads.
- Full access to all 6 frontend pages, interactive map layers, flood comparison, Saabas explainability, and historical campaign switching.
- Allows full interactive AOI drawing and real Sentinel-1 catalogue querying via NASA ASF DAAC (with offline query caching).
- Protects server compute resources by returning HTTP 403 on dynamic processing submissions and directing users to the completed campaigns.

### Private Live Processing Mode (`DEMO_MODE_RESTRICTED_EXECUTION=false`)
- Intended for authorized private or institutional environments with verified compute capacity.
- Requires ESA SNAP 10+, NASA Earthdata credentials, and local disk storage (~2 GB per scene pair).
- Automatically downloads raw Sentinel-1 IW GRD SAFE archives, executes SNAP calibration and terrain correction, applies the Refined Lee filter, performs Random Forest classification, and derives flood transitions dynamically.
- *Note:* Static web hosts (such as GitHub Pages) cannot execute Python backend services or ESA SNAP pipelines. Full live execution requires a host capable of running Python 3.10+ and the backend API server.

---

## 4. System Prerequisites

| Requirement | Minimum Version | Notes |
|:---|:---:|:---|
| **Operating System** | Linux (Ubuntu / Debian / Kali) | x86_64 architecture |
| **Python** | 3.10+ | Python 3.10–3.14 verified |
| **Node.js** | 18 LTS | Node.js 20+ LTS recommended |
| **npm** | 9+ | Included with Node.js |
| **GDAL & GEOS C libraries** | GDAL 3.4+, GEOS 3.9+ | Required for geospatial operations (`gdal-bin`, `libgdal-dev`) |
| **ESA SNAP (Optional)** | SNAP 10+ / 14.0.0 | Required only for new dynamic Level-1 SAR processing |
| **NASA Earthdata (Optional)** | URS Account | Required only for downloading raw archives from ASF DAAC |

Run the automated system prerequisite check:
```bash
bash scripts/check_prerequisites.sh
```

---

## 5. Quick Start Installation & Execution

### Method A: Automated Linux Installation (Recommended)

```bash
# 1. Clone or unpack the repository (HTTPS requires no SSH keys)
git clone https://github.com/rahator44/NASA_CHE.git EarthPulse-SAR
# (Or using SSH: git clone git@github.com:rahator44/NASA_CHE.git EarthPulse-SAR)
cd EarthPulse-SAR

# 2. Extract portable demonstration data into the project root (if not already extracted)
# Download EARTH_PULSE_PORTABLE_DEMO_DATA.zip from GitHub Releases
unzip EARTH_PULSE_PORTABLE_DEMO_DATA.zip -d .

# 3. Run automated installation (checks prerequisites, creates .venv, installs deps, builds frontend, inits DB)
bash scripts/install_linux.sh

# 4. Launch the application (Unified FastAPI + WebGIS frontend)
bash scripts/run_linux.sh
```
* **Web Application:** `http://127.0.0.1:8000`
* **Interactive API Documentation:** `http://127.0.0.1:8000/docs`
* **Service Health Check:** `http://127.0.0.1:8000/health`

### Method B: Containerized Deployment (Docker Compose)

```bash
# Start containerized application with persistent volume mount for data
docker compose up --build -d

# Check service logs and health
docker compose logs -f
curl http://localhost:8000/health
```

### Method C: Manual Step-by-Step Installation

```bash
# Backend virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize database
python3 -c "from src.backend.database.database import init_db; init_db()"

# Build React WebGIS frontend
cd frontend
npm ci
npm run build
cd ..

# Verify integrity
bash scripts/verify_integrity.sh

# Start production server
uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
```

### Optional: Enabling Private Live SAR Processing (NASA Earthdata & ESA SNAP)

By default, Earth Pulse runs in **Public Demo Mode**, allowing you to inspect all 6 WebGIS pages, explore interactive maps, and review the verified 2024 and 2025 flood campaigns without any external accounts or credentials.

To enable **dynamic processing of new Sentinel-1 acquisitions** on an authorized local workstation:

1. **Create a NASA Earthdata Account:**
   - Register at [NASA Earthdata Login (URS)](https://urs.earthdata.nasa.gov/).
   - Under **Applications** &rarr; **Authorized Apps**, authorize **Alaska Satellite Facility (ASF) DAAC**.

2. **Configure Local Credentials (`~/.netrc`):**
   ```bash
   touch ~/.netrc && chmod 0600 ~/.netrc
   echo "machine urs.earthdata.nasa.gov login <YOUR_USERNAME> password <YOUR_PASSWORD>" >> ~/.netrc
   ```

3. **Verify Earthdata Access Safely (Without Leaking Secrets):**
   ```bash
   curl -s -f -n -o /dev/null -w "Earthdata Status: HTTP %{http_code}\n" https://urs.earthdata.nasa.gov/profile
   ```

4. **Install ESA SNAP:**
   - Download ESA SNAP 10+ (with Sentinel-1 Toolbox) from [ESA STEP](https://step.esa.int/main/download/snap-download/).
   - Set the Graph Processing Tool executable path:
     ```bash
     export SNAP_GPT_PATH=/path/to/snap/bin/gpt
     ```

5. **Enable Live Processing Mode:**
   - In your `.env` file, set:
     ```bash
     DEMO_MODE_RESTRICTED_EXECUTION=false
     ```
   - Restart the server: `bash scripts/run_linux.sh`

---

## 6. Running Tests & Verification

### Complete Backend Test Suite (558 tests)
```bash
source .venv/bin/activate
pytest tests/ -q
```

### Frontend Unit Tests (22 tests)
```bash
cd frontend
npm test
```

### Full Headless Browser Smoke Test
Runs headless Chromium via Chrome DevTools Protocol (CDP), testing all 6 routes, pixel-level raster rendering, multi-viewport layout (Desktop 1440×900, Tablet 768×1024, Mobile 390×844), AOI drawing, and catalogue search:
```bash
python3 frontend/scripts/browser_smoke_test.py
```

---

## 7. Repository Structure

```text
EarthPulse-SAR/
├── configs/              # Multi-region YAML study configuration
├── docs/                 # Scientific and API documentation
│   ├── API_CONTRACT.md
│   ├── DEPLOYMENT_GUIDE.md
│   ├── DEMO_DATA_MANIFEST.json   ← Authoritative SHA-256 manifest
│   ├── MODEL_PROVENANCE.md
│   ├── SCIENTIFIC_METHODOLOGY.md
│   └── screenshots/      # Pixel-level verification screenshots
├── frontend/             # React/TypeScript WebGIS UI (Vite + Leaflet)
│   ├── src/
│   │   ├── api/          # Typed API client and scientific contract validators
│   │   ├── components/   # Map, Header, Summary, XAI components
│   │   ├── pages/        # Dashboard, Explorer, New Analysis, Comparison, XAI, Science
│   │   ├── router/       # Lightweight hash/history router
│   │   └── utils/        # WKT parsing and geodesic area calculations
│   ├── scripts/browser_smoke_test.py
│   └── package.json
├── graphs/               # Canonical ESA SNAP XML processing graph
│   └── s1_grd_calibration_terrain_correction.xml
├── models/               # Frozen machine learning artifacts
│   └── phase7a/phase7a_random_forest_model.joblib
├── src/                  # Python backend application
│   ├── acquisition/      # NASA ASF DAAC search and download manager
│   ├── backend/          # FastAPI routes, schemas, services, SQLite
│   ├── core/             # Path resolution, Earthdata auth, catalog
│   ├── ml/               # Random Forest classifier and Saabas tree-path XAI
│   └── pipeline/         # SNAP preprocessing, Otsu thresholding, riverbank analysis
├── tests/                # Automated pytest suite (558 tests)
├── data/                 # ← Populated from EARTH_PULSE_PORTABLE_DEMO_DATA.zip
│   ├── cache/catalog/    # Query-bound offline catalogue cache
│   └── runs/             # 2024 and 2025 verified scientific runs
├── .env.example          # Environment template
├── .gitignore
├── INSTALL.txt           # Demo data extraction guide
├── requirements.txt      # Python dependencies
└── README.md
```

---

## 8. License & Attribution

Released under the **MIT License**. See [`LICENSE`](./LICENSE) for full legal text.

Developed for the **NASA Space Apps Challenge 2026: Dancing with the SARs**.

**Data Providers & Attributions:**
- **Copernicus Sentinel-1 & Sentinel-2 Data:** European Space Agency (ESA) / European Commission.
- **Satellite Data Distribution:** NASA Alaska Satellite Facility (ASF) Distributed Active Archive Center (DAAC).
- **Basemap Imagery:** OpenStreetMap contributors.
