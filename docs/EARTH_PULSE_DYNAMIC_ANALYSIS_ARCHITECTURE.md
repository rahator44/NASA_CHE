# EARTH PULSE — DYNAMIC ANALYSIS ARCHITECTURE

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Application:** Earth Pulse / EarthPulse-SAR  
**Scope:** Dynamic Satellite Observation, Time-Series Intelligence & Explainable AI Backend  
**Date:** November 2026  
**Status:** Authoritative Architectural Specification  

---

## 1. EXECUTIVE ARCHITECTURAL SUMMARY

Earth Pulse has evolved from a static, historical two-date demonstration (June 10 and July 16, 2024) into a generalized, data-driven environmental observation and change-analysis backend. The platform now supports user-specified dates, arbitrary bounding boxes and sub-AOIs within the Jamuna River reach, multi-date chronological time-series sequences, and on-demand AI inference with Saabas tree-path feature attribution.

The architecture preserves all authoritative Phase 1–7 scientific algorithms, the frozen Random Forest model artifact (`phase7a_rf_jamuna_v1`), and reference benchmarks while introducing modular, stateless pipeline operators and a persistent, asynchronous job execution lifecycle.

---

## 2. SYSTEM TOPOLOGY & DIRECTORY STRUCTURE

```text
EarthPulse-SAR/
├── configs/
│   ├── features/                      # Authoritative 6-feature SAR schemas
│   ├── models/                        # Model definitions & hyperparameters
│   ├── processing/                    # Preprocessing & filtering parameters
│   └── regions/                       # Jamuna regional definitions & bounds
├── data/
│   ├── intermediate/                  # SNAP BEAM-DIMAP intermediate products
│   ├── metadata/                      # SQLite database & provenance ledgers
│   ├── outputs/                       # Authoritative historical outputs (Phase 2-7)
│   ├── processed/                     # Aligned & calibrated reference GeoTIFFs
│   ├── raw/                           # Cached raw Sentinel-1 archives
│   └── runs/                          # Per-run isolated storage (<run_id>/)
│       └── <run_id>/
│           ├── request.json           # Ingested AOI & date parameters
│           ├── scenes.json            # Discovered & selected Sentinel-1 scenes
│           ├── summary.json           # Scientific results, areas, & accounting
│           ├── timeseries.json        # Chronological trajectories & frequencies
│           ├── explanations.json      # XAI attributions & additivity checks
│           ├── rasters/               # Calibrated SAR, water masks, transitions
│           └── vectors/               # Inundation GeoJSON clusters
├── docs/                              # Technical reports & integration guides
├── graphs/
│   └── s1_grd_calibration_terrain_correction.xml # Canonical 8-node SNAP graph
├── models/
│   ├── experimental/                  # Versioned candidate models (v2)
│   ├── model_registry.json            # Immutable model version ledger
│   └── phase7a/
│       └── phase7a_random_forest_model.joblib # Frozen reference model
├── scripts/                           # Historical benchmarking & pipeline runners
├── src/
│   ├── acquisition/                   # Dynamic NASA data discovery & caching
│   │   ├── asf_client.py              # NASA ASF DAAC search wrapper
│   │   ├── download_manager.py        # Chunked download streaming & resume
│   │   └── scene_selector.py          # Orbital geometry & comparability rules
│   ├── backend/                       # FastAPI web services & SQLite persistence
│   │   ├── api/v1/endpoints/          # REST routes & XYZ tile endpoints
│   │   ├── database/                  # SQLite schema & row factory
│   │   └── services/                  # Business logic & analysis orchestration
│   ├── core/                          # Authentication & catalog orchestration
│   │   ├── earthdata_auth.py          # NASA Bearer Token & .netrc credentials
│   │   └── satellite_catalog.py       # Discovery service & endpoint health checks
│   ├── ml/                            # Machine learning & Explainable AI
│   │   ├── adapters.py                # Sensor feature extraction & physics checks
│   │   ├── explainability.py          # Saabas additive tree-path explainer
│   │   ├── random_forest.py           # Pure-NumPy vectorized Decision Tree & RF
│   │   ├── registry.py                # Model registry and metadata schemas
│   │   └── training/                  # Spatial/temporal train-val-test framework
│   └── pipeline/                      # Scientific raster processing modules
│       ├── change_detection.py        # 6-class transitions & area reconciliation
│       ├── feature_builder.py         # 6-feature tensor extraction for ML
│       ├── riverbank_analysis.py      # Transect displacement & char submergence
│       ├── sentinel1_preprocess.py    # SNAP GPT runner & sub-AOI extraction
│       ├── time_series.py             # Multi-date sequence & inundation frequency
│       └── water_classification.py    # Lee 5x5 filtering & dynamic Otsu
├── tests/                             # 388 comprehensive automated tests
└── tools/                             # CLI utilities for auth, setup & demo
```

---

## 3. COMPONENT LIFECYCLE & DATAFLOW

```mermaid
flowchart TD
    User["User Request\n(AOI WKT, Date Range, Mode)"] --> API["FastAPI Endpoint\n/api/v1/analysis-requests"]
    API --> Service["DynamicAnalysisService\n(Job Orchestrator)"]
    Service --> Catalog["SatelliteCatalogService\n(NASA ASF Search)"]
    Catalog --> Selector["SceneSelector\n(Track, Direction, Pol Check)"]
    Selector --> Downloader["DownloadManager\n(Local Cache / Streaming)"]
    Downloader --> Preprocessor["Sentinel1Preprocessor\n(ESA SNAP GPT / Sub-AOI Extractor)"]
    Preprocessor --> Classifier["DynamicWaterClassifier\n(Lee 5x5 + Dynamic Otsu)"]
    Classifier --> Detector["DynamicChangeDetector\n(6-Class Transition & Reconciliation)"]
    Detector --> Riverbank["DynamicRiverbankAnalyzer\n(Transect Migration & Char Islands)"]
    Classifier --> FeatureBuilder["SARFeatureBuilder\n(6 Standardized SAR Features)"]
    FeatureBuilder --> RF["RandomForestClassifier\n(Frozen Reference Model Inference)"]
    RF --> XAI["TreePathExplainer\n(Saabas Exact Additivity)"]
    Classifier --> TimeSeries["MultiDateTimeSeriesAnalyzer\n(Trajectory & Frequency Maps)"]
    Detector --> Storage["Per-Run Storage\ndata/runs/<run_id>/"]
    Riverbank --> Storage
    XAI --> Storage
    TimeSeries --> Storage
    Storage --> Tiles["XYZ Map Tile Service\n/api/v1/runs/<run_id>/tiles/..."]
    Storage --> Vectors["Vector GeoJSON Service\n/api/v1/runs/<run_id>/vectors/..."]
```

---

## 4. SCIENTIFIC INVARIANTS & INTEGRITY CONSTRAINTS

1. **Strict Area Conservation:**
   $$\text{Net Candidate Water Change} = \text{Gross Inundation} - \text{Gross Recession} = \text{Valid Water}(t_2) - \text{Valid Water}(t_1)$$
   The valid common comparison domain must remain strictly separated from NoData and numerical indeterminate noise floors.
2. **Empirical Observation Grounding:**
   The backend never fabricates, interpolates, or forecasts water extents for dates without genuine satellite acquisitions.
3. **Immutability of Historical Reference:**
   Original Sentinel-1 GRD archives, Phase 5 flood masks, Phase 6 riverbank migration products, and the frozen Random Forest artifact (`85038f0f...`) remain unaltered.
4. **Dynamic Spatial Referencing:**
   All newly preprocessed rasters strictly maintain EPSG:32645 (WGS 84 / UTM zone 45N) with 20.0 m x -20.0 m pixel resolution snapped to standard grid origins.

---

## 5. SCIENTIFIC VISUALIZATION & MAP-READY PAYLOAD ENGINE

For every completed dynamic analysis run, Earth Pulse generates authoritative, publication-quality visual outputs, map tiles, and downloadable assets derived strictly from real Sentinel-1 calibrated data and computed scientific rasters:

### 5.1 Visual Assets Generated per Run
1. **Processed Sentinel-1 Radar Imagery (`preview_t1_sar.png`, `preview_t2_sar.png`):**
   - Calibrated backscatter $\sigma^0$ (dB) with high dynamic range grayscale stretch ($-25\text{ dB}$ to $0\text{ dB}$).
   - Geographic coordinates (Longitude °E, Latitude °N), colorbar, UTC acquisition timestamp, orbit direction, and mission attribution.
2. **Candidate Water Classification Maps (`preview_t1_water.png`, `preview_t2_water.png`):**
   - Discrete categorical masks (Water `#08519c`, Non-Water `#d9d9d9`, Indeterminate `#a6cee3`).
   - Legend with exact calculated water surface area ($\text{km}^2$) and percentage of study area.
   - Otsu threshold indicators for copolarized (VV) and crosspolarized (VH) channels.
3. **Flood Inundation & Transition Dynamics (`preview_flood_transitions.png`):**
   - 6-class multitemporal transition palette (Persistent Water `#08519c`, Newly Inundated `#41b6c4`, Receded Water `#fe9929`, Non-Water `#cccccc`, Indeterminate `#a6cee3`).
   - Reconciled quantitative area metrics ($\text{km}^2$), percentage breakdown, and net flood change delta.
4. **Riverbank Migration & Channel Dynamics (`preview_riverbank_migration.png`):**
   - Channel dynamic corridor highlighting external bank erosion candidate zones (`#e31a1c`) and channel accretion / char emergence (`#33a02c`).
   - Geomorphic reach qualification status and lateral migration statistics.
5. **Random Forest Water Probability Maps (`rf_probability.tif`, `preview_rf_probability.png`):**
   - Georeferenced Float32 raster representing continuous pixel-level probability $P(\text{Water}) \in [0.0, 1.0]$.
   - Continuous `cividis` heatmap preview with annotated optimal decision threshold $\tau^* = 0.35$.
6. **Multi-Temporal Water Surface Trajectory Charts (`preview_timeseries_chart.png`):**
   - Quantitative time-series curve plotting water surface extent ($\text{km}^2$) across observation dates.
   - Step expansion/recession annotations and net hydrological change summaries.
7. **Visual Layer Manifest (`visual_manifest.json`):**
   - Machine-readable JSON describing bounding boxes (WGS84 and UTM 45N), center coordinates, observation dates, layer types, legend color palettes, tile URL templates, and scientific provenance.

### 5.2 Visualization API Endpoints
- `GET /api/v1/runs/{run_id}/visual-manifest`: Returns full map manifest for web GIS frontend.
- `GET /api/v1/runs/{run_id}/previews/{asset_name}`: Returns high-resolution preview PNGs with legends and scale bars.
- `GET /api/v1/runs/{run_id}/download/{asset_name}`: Streams georeferenced GeoTIFFs as file attachments.
- `GET /api/v1/runs/{run_id}/tiles/{asset_id}/{z}/{x}/{y}.png`: High-performance Web Mercator XYZ map tiles supporting SAR backscatter, water masks, flood transitions, Random Forest probabilities, and inundation frequencies.


