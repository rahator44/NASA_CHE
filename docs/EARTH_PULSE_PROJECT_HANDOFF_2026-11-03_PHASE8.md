# EARTH PULSE PROJECT HANDOFF — PHASE 8 COMPLETE
**NASA Space Apps Challenge 2026: Dancing with the SARs**  
**Study Area:** Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)  
**Date of Handoff:** November 3, 2026  
**Repository Baseline:** 315 Passing Tests (Zero Warnings, Zero Regressions)

---

## 1. Executive Summary

Phase 8 has successfully established the scientific backend and application foundation for Earth Pulse SAR. The system now exposes a production-ready, modular REST API built with FastAPI, native GDAL, SQLite3, and pure-NumPy services. All historical research from Phases 1 through 7B.1 has been integrated into structured catalogs, dynamic tile endpoints, and persisted provenance databases.

The repository test suite has expanded from **291 tests to 315 tests**, with all 24 Phase 8 scenarios passing completely.

---

## 2. Server Startup & Operational Commands

The backend service is located at `src/backend/main.py`. It requires no compilation or container daemons and runs directly on the local scientific Python environment.

### 2.1 Starting the Production Backend Server
```bash
# Navigate to project root
cd /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR

# Launch FastAPI ASGI server on port 8000
python3 -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2.2 Accessing Interactive Documentation
Once started, open any browser to:
- **Swagger Interactive UI:** `http://127.0.0.1:8000/docs`
- **ReDoc Technical Specification:** `http://127.0.0.1:8000/redoc`
- **Liveness Health Check:** `http://127.0.0.1:8000/health`
- **OpenAPI 3.1 JSON Specification:** `http://127.0.0.1:8000/openapi.json`

### 2.3 Running Full Automated Verification
```bash
# Run entire repository test suite (315 tests)
python3 -m pytest -q

# Run Phase 8 backend test suite specifically (24 tests)
python3 -m pytest -q tests/test_phase8_backend.py
```

---

## 3. Backend Architecture & Codebase Layout

```
src/backend/
├── config.py                 # Paths, environment configuration, allowed origins
├── main.py                   # FastAPI application factory, lifespan DB init, CORS
├── database/
│   └── database.py           # SQLite connection manager, jobs and analysis_runs tables
├── schemas/
│   ├── common.py             # Error, pagination, and status schemas
│   ├── region.py             # Region detail, bounding polygon, and summary schemas
│   ├── dataset.py            # Manifest record, provenance, and list schemas
│   ├── analysis.py           # Analysis module definition and run record schemas
│   ├── flood.py              # Inundation transitions, clusters, and epoch schemas
│   ├── riverbank.py          # Transect geometry, displacement, and erosion schemas
│   ├── model.py              # Model metrics, feature importances, and TreeSHAP schemas
│   ├── raster.py             # GeoTIFF metadata, band statistics, and vector schemas
│   ├── report.py             # Project report catalog and regional statistics schemas
│   └── job.py                # Job submission request, status, and output schemas
├── services/
│   ├── region_service.py     # Discovers and parses configs/regions/*.yaml dynamically
│   ├── dataset_service.py    # Queries and filters data/metadata/dataset_manifest.json
│   ├── flood_service.py      # Serves Phase 5 flood transitions, clusters, and balance
│   ├── riverbank_service.py  # Serves Phase 6/6.1/6.2 transects and displacement statistics
│   ├── model_service.py      # Serves Phase 7A/7B/7B.1 RF metrics, features, & attributions
│   ├── raster_service.py     # Native GDAL metadata, stats, and XYZ Web Mercator PNG tile renderer
│   ├── vector_service.py     # GeoJSON vector feature collection loader
│   ├── report_service.py     # Aggregates cross-phase findings and report summaries
│   └── job_service.py        # Sandboxed executor for allowlisted scientific workflows
└── api/
    └── v1/
        ├── router.py         # Consolidates all sub-routers under /api/v1 prefix
        └── endpoints/
            ├── system.py     # /health, /api/v1/system/status, /capabilities
            ├── regions.py    # /api/v1/regions, /{id}, /{id}/summary
            ├── datasets.py   # /api/v1/datasets, /{id}, /regions/{id}/datasets
            ├── analyses.py   # /api/v1/analyses, /{id}/summary, /regions/{id}/results
            ├── flood.py      # /regions/{id}/flood/{summary, transitions, clusters, uncertainty}
            ├── riverbank.py  # /regions/{id}/riverbank/{summary, transects, displacement, etc.}
            ├── models.py     # /api/v1/models, /{id}/metrics, /features, /explanations, /diagnostics
            ├── rasters.py    # /api/v1/rasters, /{id}/metadata, /{id}/statistics
            ├── vectors.py    # /api/v1/vectors, /{id}
            ├── tiles.py      # /api/v1/tiles/{asset_id}/{z}/{x}/{y}.png
            ├── reports.py    # /api/v1/reports, /{id}, /regions/{id}/statistics
            └── jobs.py       # POST /api/v1/jobs, GET /api/v1/jobs, GET /api/v1/jobs/{id}
```

---

## 4. Key Epistemological & Scientific Standards Maintained

1. **Deterministic Baseline Primacy:**
   - Operational flood inundation mapping is definitively anchored to **Adaptive Lee 5x5 Dual-AND Otsu** ($F_1 = 0.8142$).
   - The Random Forest model ($F_1 = 0.6026$, Precision = $0.4477$, Recall = $0.9214$) is retained solely as an auxiliary continuous probability layer (`RETAINED_AS_PROBABILITY_LAYER`) at $\tau^* = 0.35$.
2. **Model Integrity Preservation:**
   - `models/phase7a/phase7a_random_forest_model.joblib` has NOT been retrained or modified. Its SHA-256 remains strictly `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`.
3. **Disambiguated Base Value Standard:**
   - Both $\phi_0 = 0.4905$ (training background prior expectation) and $\phi_0 = 0.4995$ (ensemble root mean probability) are clearly separated in the API. Prior specification typo $0.3905$ is formally documented and corrected.
4. **Acquisition Calendar Year Standard:**
   - All dataset captures are confirmed to have occurred in **2024** (June 10 and July 16, 2024).
5. **Zero External Dependency Violations:**
   - Prohibited libraries (`rasterio`, `geopandas`, `shapely`, `shap`, `sklearn`) remain completely uninstalled. All geospatial reprojection and vector parsing is handled via native C++ GDAL bindings, NumPy, and standard Python libraries.

---

## 5. Ready for Phase 9 (Frontend Integration)

With Phase 8 complete, all data services required for Phase 9 (Interactive Geospatial Dashboard & Web Frontend) are immediately operational:
- **Map Layers:** Dynamic XYZ Web Mercator PNG tiles available at `/api/v1/tiles/{asset_id}/{z}/{x}/{y}.png` for all 12 flood, riverbank, and probability rasters.
- **GIS Features:** GeoJSON endpoints available at `/api/v1/vectors/{asset_id}` for transects and inundation clusters.
- **Charts & Statistics:** JSON endpoints available for flood transition balances, riverbank displacement curves, ROC curves, reliability diagrams, and TreeSHAP feature attribution waterfalls.

