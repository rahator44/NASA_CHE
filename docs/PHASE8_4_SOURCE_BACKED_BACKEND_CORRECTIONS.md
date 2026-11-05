# EARTH PULSE — PHASE 8.4: SOURCE-BACKED BACKEND CORRECTION & REGRESSION TESTING

NASA Space Apps Challenge 2026 — Dancing with the SARs  
Project: EarthPulse-SAR  
Study Area: Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)  
Date: November 5, 2026  
Status: VERIFIED & SEALED  

---

## 1. Executive Summary

Phase 8.4 executed a focused, source-backed backend correction and regression testing phase following independent code review of the EarthPulse-SAR repository (`NASA_CHE-main.zip`).

The primary objective was to align all backend data contracts, schemas, services, and endpoints directly with the authoritative bundled CSV and JSON source-of-truth files produced across Phases 1 through 7B.1. All original satellite files, completed scientific raster outputs, and the frozen Random Forest model artifact (`models/phase7a/phase7a_random_forest_model.joblib`) were strictly preserved. No new external packages were installed, and no new satellite data downloads were required.

Following the implementation of 22 specific issue resolutions across 10 backend files and the creation of `src/backend/contracts.py`, the entire repository test baseline was expanded from 24 to 39 backend tests, with all **330 tests passing cleanly with zero failures and zero warnings**.

---

## 2. Immutable Invariants & Verification

All core repository invariants were audited and verified intact:
1. **Raw Satellite Archives**:
   - `data/raw/sentinel1/`: Both original SLC/GRD ZIP archives intact.
   - `data/raw/sentinel2/`: Both MSI Level-2A archives intact.
2. **Frozen Model Artifact**:
   - Path: `models/phase7a/phase7a_random_forest_model.joblib`
   - Verified SHA-256: `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`
   - Model Status: `RETAINED_AS_PROBABILITY_LAYER` (Test ROC-AUC = 0.6810, Threshold $\tau^* = 0.35$).
3. **Primary Operational Baseline**:
   - Deterministic Dual-AND Otsu on 5x5 Adaptive Lee filtered VV/VH backscatter remains the authoritative operational flood baseline.
4. **Test Suite Baseline**:
   - Complete passing suite: **330 passed in 21.67s**.

---

## 3. Systematic Source-Backed Corrections

### A. Shared Source-of-Truth Contracts (`src/backend/contracts.py`)
Created a dedicated scientific contracts module encapsulating all authoritative constants and schemas:
- Phase 5 Common-Valid-Domain water transition accounting.
- Whole-epoch unmasked delta vs. valid-domain net change reconciliation.
- Phase 6.1 audited transect counts (154 evaluated, 122 valid, 32 outside valid-local).
- Phase 6.2 95% spatial block bootstrap confidence intervals.
- Phase 6.1 12-class geomorphic change zone codebook and color palette.
- Model registry constants, uncalibrated decision margin interpretation, and scattering hypotheses.

### B. Flood & Surface-Water Change Services (`flood_service.py`, `schemas/flood.py`)
1. **Common Valid Domain Transition Accounting**:
   - Persistent Water: 216,595 cells (86.6380 km², 8,663.80 ha, 11.47% of domain).
   - Newly Inundated Candidate: 146,992 cells (58.7968 km², 5,879.68 ha, 7.78% of domain).
   - Receded Water: 1,634 cells (0.6536 km², 65.36 ha, 0.09% of domain).
   - Persistent Non-Water: 1,523,501 cells (609.4004 km², 60,940.04 ha, 80.66% of domain).
   - Net Inundation Balance: **+5,814.32 ha** (+145,358 cells).
2. **Dual-Domain Reconciliation**:
   - Whole-Epoch Unmasked Delta: **6,452.24 ha** (161,306 cells).
   - Asymmetric Radar Mask Exclusion Gap: **637.92 ha** (15,948 cells).
   - Accounting Note explicitly explains the spatial domain distinction.
3. **Hydrological Terminology**:
   - Corrected July 16 observation label to `"Monsoon Flood-Period Observation"` (mid-monsoon high stage / anabranch expansion, not seasonal peak crest). Backward-compatible alias `monsoon_crest_epoch` maintained.
4. **Region Validation**:
   - Unknown `region_id` strictly rejected with HTTP 404.

### C. Fluvial Riverbank Migration & Displacement Services (`riverbank_service.py`, `schemas/riverbank.py`)
1. **Audited Transect Population**:
   - Total evaluated: **154** (from `phase6_1_transect_displacement_audit.csv`).
   - Valid local migration: **122** (79.22% valid fraction).
   - Outside valid-local: **32** (23 ambiguous edge effects, 5 anabranch activations, 4 major channel expansions).
   - Query `only_valid=true` returns exactly 122 transects; `only_valid=false` returns all 154.
2. **Standard Field Naming**:
   - Added `chainage_m` populated from the audit CSV; preserved `station_m` as an alias.
3. **Statistical Confidence Intervals**:
   - Removed erroneous assignment of empirical `[P10, P90]` sample percentiles as confidence bounds.
   - Wired 95% spatial block bootstrap confidence intervals from `phase6_2_spatial_bootstrap_intervals.csv`:
     - West Bank Median 95% CI: **[20.0, 80.0] m** (point median: 40.0 m).
     - East Bank Median 95% CI: **[20.0, 150.0] m** (point median: 60.0 m).
     - Channel Width Median 95% CI: **[120.0, 320.0] m** (point median: 200.0 m).
4. **Provisional Detection Range & Scenario Thresholds**:
   - Retired deprecated 53.92 m single scalar.
   - Exposed 3-tier provisional scenario thresholds: 35.0 m (steep cut-banks), 60.0 m (nominal unconsolidated bank), 85.0 m (low-gradient char fringes).
5. **Erosion Candidate Zones**:
   - Aligned with Phase 6.1 general reconciliation zones:
     - Zone 2 (External Bank Expansion): 21.9400 km² (2,194.00 ha, 54,850 cells).
     - Zone 3 (Internal Char Submergence): 23.2100 km² (2,321.00 ha, 58,025 cells).
     - Zone 4 (Apparent Contraction / Accretion): 0.4148 km² (41.48 ha, 1,037 cells).
     - Zone 6 (Disconnected Floodplain Inundation): 13.6468 km² (1,364.68 ha, 34,117 cells).

### D. Raster & Tile Services (`raster_service.py`)
1. **12-Class Geomorphic Codebook Palette**:
   - Replaced preliminary 4-class palette with the complete 12-class palette matching `phase6_1_area_reconciliation.csv` (classes 0..10 and 255 NoData).
2. **Dynamic CRS Extraction**:
   - Extracted CRS dynamically from dataset spatial reference (`ds.GetSpatialRef()`) rather than hardcoding `"EPSG:32645"`.
3. **NoData Alpha Transparency**:
   - Updated `_colorize_array` to filter out NoData sentinels (`arr <= -9990.0`) and non-finite values so they render with `alpha = 0` (fully transparent).
4. **Tile Error Logging**:
   - Added server-side `logger.error` logging with full exception tracebacks during tile generation failures.

### E. Vector Services (`vector_service.py`, `endpoints/vectors.py`)
1. **WGS84 EPSG:4326 Reprojection**:
   - In accordance with RFC 7946, native UTM Zone 45N (`EPSG:32645`) coordinates are dynamically reprojected to EPSG:4326 degrees (`[longitude, latitude]`) using GDAL/OSR `CoordinateTransformation` with traditional GIS axis ordering.
2. **Metadata Transparency**:
   - Added `native_crs: "EPSG:32645"` in the API response wrapper.
3. **Dynamic Region Association**:
   - `region_id` derived directly from asset catalog.

### F. Model & Explainability Services (`model_service.py`)
1. **Model ID Validation**:
   - Unknown model IDs strictly rejected with HTTP 404.
2. **Decision Margin Interpretation**:
   - Clarified that $|P - 0.5|$ measures distance to the uncalibrated symmetric classification boundary (0.5), not distance to the tuned operational decision threshold ($\tau^* = 0.35$).
   - Explicitly noted that uncalibrated Gini trees polarize probability distributions toward extreme values.

### G. Job & Dataset Services (`job_service.py`, `dataset_service.py`)
1. **Type Annotation Compatibility**:
   - Added `Tuple` to typing imports in `job_service.py`, eliminating potential NameError on Python 3.13 / 3.14.
2. **Streaming SHA-256 Dataset Verification**:
   - Replaced mock verification with real streaming SHA-256 calculation for registered files present on disk against `dataset_manifest.json`.
3. **Accurate Checksum Status**:
   - In `dataset_service.py`, missing files now report `checksum_verified = False` and `quality_status = "FILE_MISSING"`.

### H. Persistence & System Routing (`database.py`, `main.py`, `system.py`)
1. **Analysis Runs Seed Data**:
   - Updated SQLite seed records for `run_phase5_flood_change`, `run_phase6_riverbank_migration`, and `run_phase7a_random_forest` to match authoritative audited figures (ROC-AUC 0.6810, 154/122 transects, Common Valid Domain areas).
2. **Sanitized Global Error Handler**:
   - Logged full tracebacks on server side while returning sanitized generic JSON error responses to clients.
3. **Route Normalization**:
   - Root `/health` mounted at `/health`.
   - System router mounted cleanly under `/api/v1/system/status` and `/api/v1/system/capabilities`, completely eliminating redundant double prefixes.

---

## 4. Verification & Regression Test Results

A comprehensive 15-scenario regression test module (`tests/test_phase8_4_backend_corrections.py`) was implemented and executed:

| Test Scenario | Purpose | Result |
|---|---|---|
| `test_01_common_valid_domain_flood_transitions` | Validates 216k / 147k / 1.6k cell breakdown and 5,814.32 ha net change | **PASSED** |
| `test_02_whole_epoch_delta_vs_common_valid_reconciliation` | Reconciles 5,814.32 ha net change with 6,452.24 ha whole-epoch delta and 637.92 ha gap | **PASSED** |
| `test_03_flood_summary_terminology_and_dates` | Verifies flood observation labeling and non-peak-crest condition | **PASSED** |
| `test_04_riverbank_transects_audited_counts` | Validates 154 evaluated, 122 valid, and 32 outside valid-local transects | **PASSED** |
| `test_05_transect_field_naming_chainage` | Verifies `chainage_m` populated from audit CSV | **PASSED** |
| `test_06_spatial_bootstrap_confidence_intervals` | Verifies 95% bootstrap intervals: West [20, 80], East [20, 150], Width [120, 320] m | **PASSED** |
| `test_07_provisional_detection_scenario_thresholds` | Verifies 35m, 60m, 85m provisional detection scenarios | **PASSED** |
| `test_08_candidate_erosion_zones_phase6_1_general` | Validates Phase 6.1 general zones (21.94, 23.21, 0.4148, 13.65 km²) | **PASSED** |
| `test_09_raster_channel_change_zones_12_class_palette` | Validates complete 12-class palette covering classes 0..10 and 255 | **PASSED** |
| `test_10_dynamic_raster_crs_extraction` | Validates dynamic extraction of raster CRS from dataset projection | **PASSED** |
| `test_11_vector_epsg4326_reprojection` | Validates standard WGS84 GeoJSON reprojection and native CRS preservation | **PASSED** |
| `test_12_unknown_region_and_model_rejection` | Validates strict HTTP 404 rejection of unknown region_id and model_id | **PASSED** |
| `test_13_model_decision_margin_interpretation` | Validates uncalibrated distance to 0.5 boundary interpretation | **PASSED** |
| `test_14_dataset_integrity_job_execution` | Validates real SHA-256 streaming verification via background job | **PASSED** |
| `test_15_clean_route_paths_and_health` | Validates root `/health`, `/api/v1/system/status`, and capabilities | **PASSED** |

**Full Repository Test Execution**:
```bash
pytest tests/ -v
# Result: 330 passed in 21.67s
```

---

## 5. Deliverables & Artifact Register

1. `src/backend/contracts.py`: Authoritative scientific contracts module.
2. `tests/test_phase8_4_backend_corrections.py`: 15-scenario regression suite.
3. `data/outputs/phase8_4/issue_resolution_register.csv`: 22 resolved audit findings.
4. `data/metadata/phase8_4_correction_report.json`: Machine-readable audit report.
5. `docs/PHASE8_4_SOURCE_BACKED_BACKEND_CORRECTIONS.md`: Detailed technical documentation.
6. `docs/EARTH_PULSE_PROJECT_HANDOFF_2026-11-05_PHASE8_4.md`: Updated project handoff dossier.
