# Earth Pulse — Dancing with the SARs
### NASA Space Apps Challenge 2026

**Study Area:** Jamuna River reach (Kazipur / Sirajganj, Bangladesh)  
**Sensors:** Sentinel-1 C-band SAR (IW GRDH VV/VH), Sentinel-2 MSI Optical Level-2A  
**Architecture:** Scientific Python, NumPy-accelerated tree explainability, FastAPI synchronous backend services, GDAL/Rasterio geospatial processing  
**Test Baseline:** 337 passing tests, 0 warnings (Phases 1–8.6)

---

## 1. Executive Summary & Scientific Purpose

Earth Pulse is an automated, reproducible satellite radar and optical remote-sensing application designed to monitor catastrophic monsoon flooding, active riverbank erosion, and channel morphology changes in the braid-belt of the lower Jamuna River.

The system addresses the extreme cloud-cover bottleneck typical of South Asian monsoon events by pairing all-weather, day-and-night Synthetic Aperture Radar (SAR) backscatter analysis ($\sigma^0_{\text{VV}}$, $\sigma^0_{\text{VH}}$) with physics-informed water classification, machine learning, and explainable AI.

### Key Capabilities
- **End-to-End SAR Ingestion & Preprocessing (Phases 1–2B):** Radiometric calibration, SNAP-aligned Lee speckle filtering (5×5 window), and coregistered multi-temporal difference analysis between pre-flood (June 10, 2024) and mid-monsoon flood-period (July 16, 2024) acquisitions.
- **Physics-Informed Water Classification (Phase 3A):** Bimodal thresholding (Otsu & Kittler-Illingworth) on SAR backscatter with cross-polarization ratio ($\text{VH}/\text{VV}$) masking to eliminate false positives in urban and bare agricultural soils.
- **Rigorous Flood Change Engine (Phases 3B & 5):** Spatial-temporal change detection isolating newly inundated land, permanent water bodies, and dry land with continuous mass-balance accounting ($A_{\text{total}} = A_{\text{perm}} + A_{\text{flood}} + A_{\text{dry}}$).
- **Independent Optical Validation (Phases 4A–4D.1):** High-resolution Sentinel-2 MSI optical reference validation utilizing MNDWI, NDWI, and Scene Classification Layer (SCL) cloud masks.
- **Riverbank Displacement & Channel Migration (Phases 6–6.2):** High-precision vector shoreline extraction, normal transect spacing (200 m across 154 evaluated transects), and sub-pixel displacement calculation with uncertainty bounds separating true morphological erosion from transient flood submergence.
- **Extensible Machine Learning & Explainability (Phases 7A–7B.1):** Dual-polarization Random Forest classification with Saabas-style tree-path feature attribution implemented in pure NumPy (local additive feature contributions decomposed at float32 inference precision, without external black-box dependencies).
- **Production REST API & Synchronous Services (Phases 8–8.1):** FastAPI scientific backend featuring 44 documented endpoints, SQLite job ledger with synchronous execution, OpenAPI/Swagger interactive documentation, health monitoring, and structured error boundaries.

---

## 2. Verified Test Baseline & Quality Assurance

The complete scientific suite has been validated across 8 development phases and is governed by strict mathematical and scientific tests:

```bash
$ python3 -m pytest -q -p no:cacheprovider tests/
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 68%]
........................................................................ [ 91%]
.................................................                        [100%]
337 passed in 38.92s
```

All 337 tests pass with zero warnings and zero deprecation notices under Python 3.10+.

---

## 3. Repository Architecture

```text
EarthPulse-SAR/
├── configs/                   # Multi-region YAML configuration engine
│   ├── features/              # SAR polarization and ratio feature definitions
│   ├── models/                # Random Forest hyperparameters and training specs
│   ├── regions/               # AOI bounding boxes and coordinate reference systems
│   └── sensors/               # Sentinel-1 and Sentinel-2 sensor calibrations
├── data/
│   ├── metadata/              # Preprocessing manifests, job queues, and security audits
│   ├── outputs/               # Quantitative CSV results, maps, and GeoJSON vectors
│   │   ├── phase1_3b/         # SAR backscatter, Otsu thresholds, and flood vectors
│   │   ├── phase4/            # Optical MNDWI/NDWI reference masks and validation metrics
│   │   ├── phase5/            # Final flood change spatial accounts
│   │   ├── phase6/            # Channel bank migration transects and erosion rates
│   │   ├── phase7a/           # Random Forest probability maps and confusion matrices
│   │   ├── phase7b/           # Saabas-style tree attribution explainability rasters
│   │   ├── phase8_1/          # Handoff manifests and API route registers
│   │   └── phase8_3/          # GitHub and Google Drive file transfer inventories
│   ├── raw/                   # [Google Drive] Original Sentinel-1 GRD SAFE archives
│   ├── reference/             # [Google Drive] Sentinel-2 MSI optical reference archives
│   └── intermediate/          # [Google Drive] Calibrated Sigma0 rasters
├── docs/                      # Comprehensive phase-by-phase scientific documentation
├── models/
│   ├── model_registry.json    # Machine learning model metadata and tracking
│   └── phase7a/               # Serialized Random Forest model artifact (.joblib, 104 KB)
├── scripts/                   # Scientific execution and reproduction scripts (Phases 1–8)
├── src/                       # Core scientific Python modules
│   ├── backend/               # FastAPI microservices, routers, job workers, schemas
│   ├── core/                  # Raster I/O, coregistration, coordinate transformations
│   └── ml/                    # Random Forest, feature engineering, tree explainability
├── tests/                     # 337 unit, integration, and mathematical verification tests
├── tools/                     # Data restoration, Drive staging, and verification tools
│   ├── restore_earthpulse_data.py
│   └── stage_earthpulse_drive_data.py
├── EARTH_PULSE_INDEPENDENT_REVIEW.md  # External code reviewer guidance
├── pyrightconfig.json         # Static analysis configuration
├── requirements.txt           # Python dependency specifications
└── README.md                  # This file
```

---

## 4. Quickstart: Installation & Running the System

### 4.1 Prerequisites
- Linux / macOS / Windows WSL2
- Python 3.10, 3.11, or 3.12
- GDAL binaries (`libgdal-dev` on Debian/Ubuntu)

### 4.2 Installation
```bash
git clone https://github.com/rahator44/NASA_CHE.git EarthPulse-SAR
cd EarthPulse-SAR

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.3 Running the Test Suite
```bash
python3 -m pytest -v tests/
```

### 4.4 Launching the Backend REST API
```bash
python3 src/backend/main.py
```
Or via Uvicorn:
```bash
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Once launched, open your browser to inspect interactive API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- System Health Check: `http://localhost:8000/health`

---

## 5. Large Scientific Data & Google Drive Restoration

To maintain a fast and lightweight GitHub repository, large binary satellite archives and processed GeoTIFFs (~5.6 GB) are hosted on Google Drive:

- **Target Google Account:** `pillior44@gmail.com`
- **Staging Folder:** `EarthPulse-SAR-Scientific-Data/`

### Restoring Large Data
Once downloaded from Google Drive, verify and restore the data with a single command:

```bash
# Verify checksums of existing repository files
python3 tools/restore_earthpulse_data.py --verify-only

# Dry run restoration from downloaded Google Drive folder
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --dry-run

# Execute full restore (copies or symlinks files into data/raw, data/reference, etc.)
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --mode copy
```

Every restored file is verified on the fly against the cryptographic SHA-256 database in `data/outputs/phase8_3/checksum_verification.csv`.

---

## 6. Independent Reviewer Information

For independent external reviewers (e.g., ChatGPT / Claude / Gemini), please consult:
[`EARTH_PULSE_INDEPENDENT_REVIEW.md`](./EARTH_PULSE_INDEPENDENT_REVIEW.md)

It contains:
- Complete system overview and architecture rationale
- Step-by-step test execution commands
- Backend API validation scripts
- Machine learning verification protocols
- Known non-blocking items from the Phase 8.1 handoff audit

---

## 7. License & Attribution

Developed for **NASA Space Apps Challenge 2026 — Dancing with the SARs**.  
Data acknowledgments: European Space Agency (ESA) Copernicus Sentinel-1 & Sentinel-2 Open Access Hub.
