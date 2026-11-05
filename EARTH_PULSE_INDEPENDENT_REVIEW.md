# EarthPulse-SAR — Independent Code Review & Evaluation Guide
### NASA Space Apps Challenge 2026 — Dancing with the SARs

**Project Root:** `EarthPulse-SAR/`  
**Current Baseline:** 315 Passing Tests (0 Failures, 0 Warnings)  
**Target Reviewer:** External AI System / Independent Software Auditor (e.g., ChatGPT)  
**Study Region:** Jamuna River reach, Kazipur / Sirajganj, Bangladesh (UTM Zone 45N / EPSG:32645)

---

## 1. Executive Summary & Review Scope

Earth Pulse is an automated, reproducible satellite radar and optical remote-sensing application designed to monitor catastrophic monsoon flooding, active riverbank erosion, and channel morphology changes in the braid-belt of the lower Jamuna River.

This document serves as an exhaustive, self-contained evaluation guide for an independent external reviewer. It details:
1. System architecture and design principles.
2. Verified test suite execution and test coverage.
3. FastAPI scientific backend service operation.
4. Machine learning pipeline (Random Forest) and Explainable AI (NumPy-accelerated tree path attribution).
5. Fluvial geomorphological bank migration mechanics.
6. Large scientific data restoration workflow (Google Drive).
7. Known non-blocking audit items and recommended forward actions.

---

## 2. System Verification & Test Suite Execution

The repository maintains strict quality assurance across all completed phases (1 through 8.1).

### 2.1 Running the Full Test Suite
Execute the entire test suite in your local environment:

```bash
# Set Python path and prevent bytecode clutter
export PYTHONPATH=.
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -v tests/
```

### 2.2 Expected Test Outcome
- **Total Tests:** 315
- **Failures:** 0
- **Errors:** 0
- **Warnings:** 0
- **Execution Time:** ~14–16 seconds on standard x86_64 CPU

### 2.3 Test Suite Breakdown
| Test Category | Target Subsystem | Test File | Test Count |
| :--- | :--- | :--- | :--- |
| **SAR Preprocessing** | Radiometric calibration, SNAP-aligned Lee filtering | `tests/test_sar_preprocessing.py` | 38 |
| **Water Classification** | Bimodal Otsu, Kittler-Illingworth, $\text{VH}/\text{VV}$ ratio masking | `tests/test_water_classification.py` | 42 |
| **Flood Detection** | Temporal change engine, inundation cluster metrics | `tests/test_flood_detection.py` | 35 |
| **Optical Reference** | Sentinel-2 MNDWI, SCL cloud masking, confusion matrix | `tests/test_optical_validation.py` | 45 |
| **Riverbank Morphology**| Shoreline extraction, normal transects, migration bounds | `tests/test_riverbank_migration.py` | 44 |
| **Machine Learning** | Random Forest model, feature pipeline, configuration | `tests/test_random_forest.py` | 30 |
| **Explainable AI** | NumPy tree-path attribution, SHAP equivalence, axioms | `tests/test_explainability.py` | 26 |
| **Backend API** | FastAPI routers, services, job queue, error handling | `tests/test_backend.py` | 55 |
| **Total** | **Full System Integration Baseline** | | **315** |

---

## 3. Backend API Architecture & Live Inspection

The scientific backend is built on FastAPI and Uvicorn, exposing 44 REST endpoints across 6 core routers.

### 3.1 Launching the API Service
```bash
# Launch backend service on port 8000
python3 src/backend/main.py
```
Or directly with Uvicorn:
```bash
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
```

### 3.2 Key Endpoints for Reviewer Verification
1. **System Health & Capabilities:**
   - `GET /health` — Microservice uptime, memory consumption, worker thread status.
   - `GET /api/v1/system/status` — Processing engine status and storage mounts.
   - `GET /api/v1/system/capabilities` — Algorithmic feature matrix (SAR, ML, XAI, Morphology).
2. **Interactive Documentation:**
   - `http://localhost:8000/docs` — Swagger UI with interactive parameter test benches.
   - `http://localhost:8000/redoc` — ReDoc specification.
3. **Flood Change Analysis:**
   - `GET /api/v1/analysis/flood-summary` — Pre-flood vs peak-flood inundation mass-balance statistics ($km^2$).
   - `GET /api/v1/analysis/water-balance` — Water area accounting.
4. **Fluvial Geomorphology & Riverbank Migration:**
   - `GET /api/v1/riverbank/summary` — Validated transect count (122 valid / 53 ambiguous char splits), mean migration rate.
   - `GET /api/v1/riverbank/transects` — GeoJSON transect lines with erosion/accretion flags.
5. **Machine Learning & Model Inference:**
   - `GET /api/v1/ml/model-info` — Hyperparameters, feature importances, calibration metrics of the Phase 7A Random Forest.
   - `POST /api/v1/ml/predict-pixel` — Point-based backscatter inference with confidence intervals.
6. **Explainable AI & Feature Attribution:**
   - `POST /api/v1/explainability/explain-pixel` — Real-time NumPy tree-path attribution computing exact Shapley values.
7. **Vector & Raster Asset Catalog:**
   - `GET /api/v1/vectors/catalog` — Available GeoJSON layers.
   - `GET /api/v1/rasters/catalog` — Available calibrated GeoTIFF layers.
8. **Asynchronous Job Management:**
   - `GET /api/v1/jobs/` — SQLite-backed asynchronous execution queue.
   - `POST /api/v1/jobs/submit` — Submit asynchronous analysis pipeline run.

---

## 4. Machine Learning & Explainable AI Architecture

### 4.1 Random Forest Pipeline (Phase 7A)
- **Model File:** `models/phase7a/phase7a_random_forest_model.joblib` (104 KB, committed to GitHub).
- **Features Used:**
  1. $\sigma^0_{\text{VV}}$ (Decibels)
  2. $\sigma^0_{\text{VH}}$ (Decibels)
  3. Polarization Ratio ($\text{VH}/\text{VV}$)
  4. Difference Ratio ($\Delta \text{VV} = \sigma^0_{\text{VV, post}} - \sigma^0_{\text{VV, pre}}$)
  5. Difference Ratio ($\Delta \text{VH} = \sigma^0_{\text{VH, post}} - \sigma^0_{\text{VH, pre}}$)
- **Cross-Region Extensibility:** All region coordinates, sensor parameters, and model specifications are abstracted into `configs/` (`configs/regions/jamuna_sirajganj.yaml`, `configs/sensors/sentinel1.yaml`, etc.), allowing zero-code re-targeting to other river basins.

### 4.2 Custom NumPy Tree Path Attribution (Phase 7B & 7B.1)
Rather than relying on non-deterministic sampling approximations, Earth Pulse implements an exact tree-path traversal algorithm in pure NumPy (`src/ml/explainability.py`).
- **Axiomatic Guarantees:**
  - *Local Accuracy (Efficiency):* $\sum_{i=1}^{M} \phi_i(x) = f(x) - \mathbb{E}[f(X)]$. The sum of feature attributions equals the difference between model output and baseline prediction.
  - *Missingness (Null Attribution):* Features that do not contribute to tree splits receive exactly zero attribution.
  - *Mathematical Equivalence:* Fully verified against exact TreeSHAP expectations with zero external C++ library dependency overhead.

---

## 5. Fluvial Geomorphology & Riverbank Migration (Phase 6–6.2)

### 5.1 Methodology
- High-precision water-land boundary extraction using zero-crossing contour tracing on coregistered 10 m SAR backscatter rasters.
- Transect generation spaced at regular 100 m intervals along the centerline of the Jamuna braid-belt.
- Normal intersection displacement measuring bank advance (accretion) and retreat (erosion).

### 5.2 Critical Scientific Reconciliation
A key finding from the Phase 6.1 & 6.2 audit:
- In active braided rivers, transient monsoon flood inundation of low-elevation sandbars (*chars*) can be easily misclassified as lateral bank retreat.
- The Earth Pulse engine introduces an ambiguity classification: of 175 total transects, **122 are verified true channel-margin displacements**, while **53 are flagged as ambiguous char submergence splits**, preventing false erosion claims.

---

## 6. Large Scientific Data Ingestion & Google Drive Restoration

The core GitHub repository contains all code, tests, documentation, vectors, metadata, and the trained model artifact (~89 MB).

The raw satellite archives and processed GeoTIFFs (~5.6 GB) are staged in a standardized Google Drive folder:
- **Google Account:** `pillior44@gmail.com`
- **Drive Staging Folder:** `EarthPulse-SAR-Scientific-Data/`

### Restoring Data Locally
```bash
# Step 1: Verify current repository integrity
python3 tools/restore_earthpulse_data.py --verify-only

# Step 2: Restore satellite rasters from downloaded Drive folder
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --mode copy
```

Every restored file is checked against `data/outputs/phase8_3/checksum_verification.csv` (SHA-256).

---

## 7. Known Phase 8.1 Audit Items (Non-Blocking)

From the pre-release Phase 8.1 Backend Readiness Audit (`data/outputs/phase8_1/issue_register.csv`), 8 minor non-blocking items were identified for future frontend integration:

1. **ISSUE-01 (Routing):** OpenAPI schema exposes 44 endpoints instead of 32 due to legacy double-prefix route aliases (`/api/v1/api/v1/system/status`). Both endpoints function correctly and return identical valid payloads.
2. **ISSUE-02 (Dependencies):** Resolved — `requirements.txt` has been created in the repository root.
3. **ISSUE-03 (Extensibility):** `VectorAssetResponse` default parameter reports `"jamuna_sirajganj"` for Jamuna assets.
4. **ISSUE-04 (CRS Metadata):** Raster metadata endpoint defaults CRS reporting to `"EPSG:32645"` (accurate for Jamuna UTM Zone 45N).
5. **ISSUE-05 (Performance):** Vector endpoints serve raw uncompressed GeoJSON (up to 4.2 MB for large candidate polygons); recommendation for Phase 9 is GZipMiddleware or vector tiles.
6. **ISSUE-06 (Job Queue):** Job execution runs synchronously on submission; cancellation API can be added in Phase 9.
7. **ISSUE-07 (Matplotlib Warning):** Standalone CLI scripts outside the backend may emit a non-fatal cache warning on stderr (`MPLCONFIGDIR=/tmp`).
8. **ISSUE-08 (Documentation Baseline):** Historical reports noted 134 transects (Phase 6.0 draft) vs 122 reconciled transects (Phase 6.1 authoritative). The backend serves the authoritative 122 count.

---

## 8. Evaluator Review Checklist

When conducting your review, you are encouraged to evaluate:
- [ ] Code cleanliness, modularity, and adherence to PEP 8 / type hints.
- [ ] Mathematical rigor of the tree attribution algorithm (`src/ml/explainability.py`).
- [ ] Correctness of SAR speckle filtering and radiometric calibration (`src/core/`).
- [ ] Integrity and reproducibility of the 315-test baseline.
- [ ] REST API schema completeness and error handling (`src/backend/`).
- [ ] Robustness of data restoration and cryptographic checksum tracking (`tools/restore_earthpulse_data.py`).

*Thank you for evaluating Earth Pulse — Dancing with the SARs (NASA Space Apps Challenge 2026).*
