# EARTH PULSE — COMPREHENSIVE PROJECT HANDOFF & SCIENTIFIC AUDIT
**Date:** 2026-11-01  
**Project:** NASA Space Apps Challenge 2026 — *"Dancing with the SARs"*  
**System:** Earth Pulse — Automated Satellite Radar Flood Inundation & Change Detection Engine  
**Target Study Area:** Jamuna River, Kazipur & Sirajganj Districts, Bangladesh  
**Target Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Raster Grid:** EPSG:32645 (UTM Zone 45N), $20.0\text{ m}$ pixel spacing, $1405 \times 1393$ cells ($1,957,165$ cells, $782.87\text{ km}^2$)  
**Current Milestone Completed:** Phase 4C.1 (Sentinel-2 Real Data Ingestion & Quality Assessment)  
**Next Milestone Planned:** Phase 4D (Independent Reference Validation Execution: Precision, Recall, F1, IoU against Sentinel-2 Clear-Sky Observations)  

---

## 1. Executive Summary & Current Operational State

Earth Pulse has completed **Phases 0 through 4C.1**. All scientific pipelines, multi-temporal change detection algorithms, quality-control audits, reference-data ingestion frameworks, and real optical reference ingestion pipelines are fully operational, verified, and backed by a comprehensive automated test suite of **153 passing unit tests** (0 failures).

Between the pre-monsoon baseline (June 10, 2024) and peak monsoon surge (July 16, 2024), the primary pipeline detects a net open candidate water expansion of **$+58.1432\text{ km}^2$** ($+145,358\text{ pixels}$) within the Kazipur study AOI. All candidate changes are designated as **provisional candidate surface water** pending independent reference validation.

Phase 4A established the validation framework, and Phase 4B/4B.1 built the complete ingestion engine. In **Phase 4C.1**, real Sentinel-2 Level-2A optical data for June 07 and July 17, 2024 was ingested, calibrated, and registered:
- **June 07, 2024:** $55.78\%$ usable clear sky in AOI ($563,408\text{ pixels}$), status: **`READY`** for validation ($\Delta t = 3\text{ days}$ from June 10 SAR).
- **July 17, 2024:** $14.82\%$ usable clear sky in AOI ($149,718\text{ pixels}$, $84.97\%$ cloud-occluded), status: **`PARTIALLY_USABLE`** for masked pixel validation ($\Delta t = 1\text{ day}$ from July 16 SAR).
- Independent reference data status in registry: **`READY`** (Optical reference datasets registered with authentic citations and verified SHA-256 digests).

---

## 2. Hardware & Software Environment

- **Operating System:** Linux (Ubuntu/Debian x86_64, Kernel 6.x)
- **CPU:** Intel Core i7-1255U (12th Gen, 10 Cores, 12 Threads)
- **Memory:** 16 GB Physical RAM
- **Execution Mode:** CPU-only (Zero GPU or CUDA requirements)
- **Core Stack:** Python 3.12+, GDAL 3.8.4 (`osgeo.gdal`, `osgeo.ogr`, `osgeo.osr`), NumPy 1.26+, SciPy 1.11+, Matplotlib 3.8+, Pytest 9.x.

---

## 3. Complete Phase-by-Phase Milestone History

### Phase 0: Project & Dataset Read-Only Audit
- Verified integrity of raw Sentinel-1 Level-1 GRD ZIP archives:
  - `S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69.zip` (1.74 GB)
  - `S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511.zip` (1.04 GB)
- Verified SNAP Range-Doppler terrain-corrected DIMAP products (`.dim` / `.data`). Confirmed `thermalNoiseCorrectionPerformed = false` in SAFE metadata, ensuring SNAP applied thermal noise subtraction exactly once.

### Phase 1: Raster Harmonization Engine
- **Script:** [`scripts/align_sar_rasters.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/align_sar_rasters.py) | **Tests:** [`tests/test_phase1_alignment.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase1_alignment.py) (10 tests)
- Harmonized June 10 ($1405 \times 1393$) and July 16 ($1406 \times 1393$) onto an identical $1405 \times 1393$ UTM grid (EPSG:32645, 20 m).
- Outputs: [`data/processed/aligned/june10_aligned.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/aligned/june10_aligned.tif), [`data/processed/aligned/july16_aligned.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/aligned/july16_aligned.tif).
- Band 1 = `Sigma0_VH`, Band 2 = `Sigma0_VV`, NoData = `-9999.0`.

### Phase 2A: Radiometric Analysis & Backscatter Characterization
- **Script:** [`scripts/analyze_backscatter_phase2a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/analyze_backscatter_phase2a.py) | **Tests:** [`tests/test_phase2a_backscatter.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_backscatter.py) (9 tests)
- Converted linear backscatter to decibels ($\sigma^0_{\text{dB}} = 10\log_{10}\sigma^0$). Generated temporal difference maps ($\Delta = \text{July} - \text{June}$).
- Identified extreme temporal differences ($> +70\text{ dB}$, up to $+91.5\text{ dB}$) and minimum values near $-105.9\text{ dB}$.

### Phase 2A.1: Quality Control & Anomaly Investigation
- **Script:** [`scripts/quality_check_phase2a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/quality_check_phase2a.py) | **Tests:** [`tests/test_phase2a_quality.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_quality.py) (5 tests)
- Investigated distribution of low backscatter ($< -20\text{ dB}$ to $< -50\text{ dB}$). Established that extreme positive differences are logarithmic division artifacts over software noise floor.

### Phase 2A.2: Scientific Interpretation Correction
- **Script:** [`scripts/verify_scientific_corrections.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/verify_scientific_corrections.py) | **Tests:** [`tests/test_phase2a_scientific_correction.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_scientific_correction.py) (5 tests)
- Proved that $-105.9\text{ dB}$ ($2.55 \times 10^{-11}$) originates from SNAP `ThermalNoiseRemovalOp` clamping intensity constant $I = 1.0 \times 10^{-5}$, not physical ground scattering.
- Retracted $-35\text{ dB}$ as an exact physical noise floor (NESZ is $-22$ to $-28\text{ dB}$). Categorized sub-detection pixels as Indeterminate, never confirmed water.

### Phase 2B: Adaptive SAR Speckle Filtering & Evaluation
- **Script:** [`scripts/filter_sar_phase2b.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/filter_sar_phase2b.py) | **Tests:** [`tests/test_phase2b_filtering.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2b_filtering.py) (14 tests)
- Evaluated Lee 3×3 and Lee 5×5 filters strictly in linear power. Created dedicated quality masks isolating clamping-floor pixels.
- Outputs: `data/processed/phase2b/lee_3x3/`, `data/processed/phase2b/lee_5x5/`, `data/processed/phase2b/quality_mask/`.

### Phase 3A: Water Classification & Threshold Benchmarking
- **Script:** [`scripts/classify_water_phase3a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/classify_water_phase3a.py) | **Tests:** [`tests/test_phase3a_classification.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase3a_classification.py) (12 tests)
- Benchmarked 36 candidate masks combining 3 filters (Unfiltered, Lee 3×3, Lee 5×5), 2 dates, and 6 algorithms (VV Otsu, VH Otsu, Dual-AND, Dual-OR, Cross-Ratio, Bivariate 2D Otsu).

### Phase 3A.1: Classification Quality Audit & Single-Pol Mask Correction
- **Script:** [`scripts/audit_phase3a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/audit_phase3a.py) | **Tests:** [`tests/test_phase3a_qc.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase3a_qc.py) (14 tests)
- Corrected single-polarization masks to incorporate Category 2 (indeterminate/clipping floor) pixels. Produced 36 certified candidate masks in `data/processed/phase3a_qc/candidate_masks/`.

### Phase 3B: Multi-Temporal Flood-Change Detection Engine
- **Script:** [`scripts/detect_flood_change_phase3b.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/detect_flood_change_phase3b.py) | **Tests:** [`tests/test_phase3b_change_detection.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase3b_change_detection.py) (15 tests)
- Developed multi-temporal change detection engine comparing June 10 and July 16 masks across 4 configurations (Primary Lee 5×5 Dual-AND, 2D Otsu, Lee 3×3, Unfiltered).
- Extracted 8-connectivity connected components and vectorized 6,725 polygons into `newly_inundated_candidate.geojson`.

### Phase 3B.1: Transition Classification & Full-Scene NoData Audit
- **Script:** [`scripts/audit_phase3b_qc.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/audit_phase3b_qc.py) | **Tests:** [`tests/test_phase3b_qc.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase3b_qc.py) (10 tests)
- Investigated conversational reporting discrepancy (595,953 Indeterminate vs 284 NoData). Proved underlying rasters and JSON reports were 100% correct all along ($577,307\text{ NoData cells} = 29.50\%$, $18,930\text{ Indeterminate cells} = 0.97\%$).
- Formally reconciled full scene and AOI metrics. Outputted certified QC products in `data/processed/phase3b_qc/` and `data/outputs/phase3b_qc/`.

### Phase 4A: Independent Flood Validation Framework & Protocol
- **Script:** [`scripts/validate_reference_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/validate_reference_data.py) | **Tests:** [`tests/test_phase4a_validation.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4a_validation.py) (12 tests)
- Audited workspace for independent reference data across 10 categories (found 0 local datasets; validation status: `BLOCKED_REFERENCE_DATA_MISSING`).
- Established evidence taxonomy (Event Docs $\ne$ Gauge Corroboration $\ne$ Pixel Validation $\ne$ Terrain Context).
- Implemented full validation metrics engine (Precision, Recall, F1, IoU, Specificity, Balanced Accuracy, NoData/Uncertainty exclusions).
- Designed ingestion specifications for Sentinel-2, Landsat, BWDB river gauges, DEM/HAND, and spatial block cross-validation.
- Generated protocol document [`docs/PHASE4A_VALIDATION_PROTOCOL.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4A_VALIDATION_PROTOCOL.md) and registry [`data/metadata/reference_data_registry.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/reference_data_registry.json).

### Phase 4A.1: Scientific Provenance & Validation Assumption Audit
- **Report:** [`docs/PHASE4A_PROVENANCE_AUDIT.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4A_PROVENANCE_AUDIT.md) | **Tests:** [`tests/test_phase4a_provenance.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4a_provenance.py) (8 tests)
- Audited all hydrological constants (SW46.9, SW46.9A, SW46.8, coordinates, danger levels, PWD datum offset) and terrain assumptions (11-18m elevation, 3m HAND cutoff, Barind Tract >25m).
- Classified unverified parameters as `UNVERIFIED` or `ASSUMPTION` and quarantined them from automatic operational execution.
- Enhanced validation metrics engine to document zero-division edge cases via explicit `class_distribution_flags`.
- Added automated gatekeepers rejecting unverified gauge observations (`validate_gauge_reading_input`) and uncalibrated terrain thresholds (`validate_terrain_threshold_input`).
### Phase 4B: Independent Reference Data Ingestion Framework
- **Scripts:** [`scripts/ingest_reference_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/ingest_reference_data.py), [`scripts/validate_reference_inputs.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/validate_reference_inputs.py) | **Tests:** [`tests/test_reference_ingestion.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_reference_ingestion.py) (18 tests)
- Built full ingestion infrastructure for Sentinel-2 Level-2A (MNDWI, AWEI_nsh, SCL cloud masking, area-weighted 10m->20m aggregation), Landsat 8/9 Level-2 (QA_PIXEL bitmasking, USGS scaling, 30m->20m spatial alignment), BWDB river stage CSVs, and Copernicus GLO-30.
- Implemented Provenance-Aware Reference Data Registry with SHA-256 cryptographic tracking and anti-circular validation guards.
- Documentation: [`docs/PHASE4B_REFERENCE_DATA_INGESTION.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4B_REFERENCE_DATA_INGESTION.md) and [`data/metadata/phase4b_ingestion_status.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase4b_ingestion_status.json).

### Phase 4B.1: Reference Ingestion Scientific Corrections & Acquisition Readiness
- **Scripts:** [`scripts/ingest_reference_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/ingest_reference_data.py), [`scripts/validate_reference_inputs.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/validate_reference_inputs.py) | **Tests:** [`tests/test_phase4b_scientific_corrections.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4b_scientific_corrections.py) (12 tests)
- Corrected Sentinel-2 SCL mapping: Class 2 is explicitly classified as Dark Area Pixels (uncertain dark observation, distinct from Class 3 cloud shadows and Class 6 water).
- Implemented dynamic per-band `BOA_ADD_OFFSET` and `QUANTIFICATION_VALUE` metadata verification across ESA Processing Baselines (enforcing offsets for Baseline $\ge 04.00$).
- Preserved native 30 m resolution metadata for Landsat Level-2, documented resampling smoothing effects, integrated `QA_RADSAT` radiometric saturation masking, and provided 60 m block aggregation comparison protocol.
- Reclassified Copernicus GLO-30 accurately as a Digital Surface Model (DSM), documenting canopy (3–15 m) and building biases, and disclaiming bare-earth HAND modeling without hydrologic conditioning.
- Enforced hydrological datum safety (`DATUM_INCOMPATIBILITY_PROTECTION` for PWD / EGM2008), preserved raw observations unaltered, and replaced hardcoded bounds with configurable plausibility warnings.
- Documentation: [`docs/PHASE4B_SCIENTIFIC_CORRECTION_REPORT.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4B_SCIENTIFIC_CORRECTION_REPORT.md), [`docs/PHASE4B_MANUAL_DATA_ACQUISITION_GUIDE.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4B_MANUAL_DATA_ACQUISITION_GUIDE.md), and [`data/metadata/phase4b_scientific_correction_report.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase4b_scientific_correction_report.json).
- Test suite expanded to **144 passed unit tests** across 13 test modules.

### Phase 4C.1: Sentinel-2 Real Data Ingestion & Quality Assessment
- **Scripts:** [`scripts/ingest_sentinel2_real.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/ingest_sentinel2_real.py), [`scripts/ingest_reference_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/ingest_reference_data.py) | **Tests:** [`tests/test_phase4c1_s2_ingestion.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4c1_s2_ingestion.py) (9 tests)
- Ingested two real Sentinel-2 Level-2A `.SAFE.zip` archives:
  - June 07, 2024: SHA-256 `e4d9ecd24029af5f370fb994c4676370ea5a2a208995edc625feb4db34b53192` (paired with June 10 SAR, $\Delta t = 3\text{ days}$).
  - July 17, 2024: SHA-256 `705d2d667e5fe7693e8b5a818eb4ba232baed7bac4be9403645eb2d4437bead4` (paired with July 16 SAR, $\Delta t = 1\text{ day}$).
- Implemented selective extraction (B03, B08, B11, B12, SCL, XML) achieving an $85\%$ reduction in storage footprint ($\sim 312\text{ MB}$ per acquisition).
- Applied dynamic Baseline 05.10 calibration: `BOA_QUANTIFICATION_VALUE = 10000`, `BOA_ADD_OFFSET = -1000`.
- Resampled to canonical SAR $20\text{ m}$ grid (EPSG:32645, $1405 \times 1393$) via area-weighted averaging (`gdal.GRA_Average`) for continuous bands and Nearest-Neighbour for SCL.
- Derived continuous spectral water indices (MNDWI, AWEI_nsh) and rigorous SCL quality masks (isolating Class 2 Dark Area Pixels as code `252`).
- Certified AOI quality assessment: June 07 status **`READY`** ($55.78\%$ clear, $25.41\%$ water = $102.65\text{ km}^2$); July 17 status **`PARTIALLY_USABLE`** ($14.82\%$ clear, $9.81\%$ water = $39.65\text{ km}^2$, $84.97\%$ cloud-occluded).
- Registered datasets into [`data/metadata/reference_data_registry.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/reference_data_registry.json).
- Documentation: [`docs/PHASE4C1_SENTINEL2_INGESTION_REPORT.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4C1_SENTINEL2_INGESTION_REPORT.md) and [`data/metadata/phase4c1_sentinel2_ingestion_report.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase4c1_sentinel2_ingestion_report.json).
- Test suite expanded to **153 passed unit tests** across 14 test modules.

---

## 4. Primary Certified Analytical Inundation Results

### A. Kazipur Study AOI ($404.02\text{ km}^2$, $1,010,039$ Cells)

| Transition Class Name | Code | Cell Count | Area (km²) | Area (ha) | % of Total AOI | % of Valid Domain |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Persistent Water** | 1 | 216,595 | 86.6380 | 8,663.80 | 21.44% | 21.80% |
| **Newly Inundated Candidate** | 2 | 146,992 | 58.7968 | 5,879.68 | 14.55% | 14.79% |
| **Receded Water** | 3 | 1,634 | 0.6536 | 65.36 | 0.16% | 0.16% |
| **Persistent Non-Water** | 4 | 628,515 | 251.4060 | 25,140.60 | 62.23% | 63.25% |
| **Indeterminate / Clipping Floor** | 5 | 16,242 | 6.4968 | 649.68 | 1.61% | — |
| **NoData / Invalid Boundary** | 6 | 61 | 0.0244 | 2.44 | 0.006% | — |
| **Total Sum** | — | **1,010,039** | **404.0156** | **40,401.56** | **100.00%** | **100.00%** |

### B. Mathematical Reconciliation Identity
$$\text{Gross Expansion } (+58.7968\text{ km}^2) - \text{Gross Recession } (-0.6536\text{ km}^2) \equiv \mathbf{+58.1432\text{ km}^2}$$
$$\text{July Valid Water } (363,587\text{ px}) - \text{June Valid Water } (218,229\text{ px}) \equiv \mathbf{+145,358\text{ px}} = \mathbf{+58.1432\text{ km}^2}$$
*Identity holds to the single pixel (0 discrepancy).*

### C. Full Raster Extent ($782.87\text{ km}^2$, $1,957,165$ Cells)
- **Persistent Water:** $250,766\text{ cells}$ ($100.3064\text{ km}^2$, $12.81\%$)
- **Newly Inundated Candidate:** $200,211\text{ cells}$ ($80.0844\text{ km}^2$, $10.23\%$)
- **Receded Water:** $2,145\text{ cells}$ ($0.8580\text{ km}^2$, $0.11\%$)
- **Persistent Non-Water:** $907,806\text{ cells}$ ($363.1224\text{ km}^2$, $46.38\%$)
- **Indeterminate / Clipping Floor:** $18,930\text{ cells}$ ($7.5720\text{ km}^2$, $0.97\%$)
- **NoData / Invalid Boundary:** $577,307\text{ cells}$ ($230.9228\text{ km}^2$, $29.50\%$)
- **Conservation Sum:** Exactly $1,957,165\text{ cells}$ ($100.000\%$).

---

## 5. Automated Test Suite Status

The automated test suite contains **114 tests** passing at a $100\%$ success rate:
- `test_phase1_alignment.py`: 10 passed
- `test_phase2a_backscatter.py`: 9 passed
- `test_phase2a_quality.py`: 5 passed
- `test_phase2a_scientific_correction.py`: 5 passed
- `test_phase2b_filtering.py`: 14 passed
- `test_phase3a_classification.py`: 12 passed
- `test_phase3a_qc.py`: 14 passed
- `test_phase3b_change_detection.py`: 15 passed
- `test_phase3b_qc.py`: 10 passed
- `test_phase4a_validation.py`: 12 passed
- `test_phase4a_provenance.py`: 8 passed
**Total: 114 passed in ~11.0 seconds.** Command: `python3 -m pytest -q tests/`

---

## 6. Directory Structure & Key Deliverables

```text
EarthPulse-SAR/
├── data/
│   ├── raw/sentinel1/                  # Original S1A Level-1 GRD ZIPs
│   ├── intermediate/                   # Original SNAP .dim / .data TC products
│   ├── reference/                      # Phase 4A reference data structure
│   │   ├── optical/                    # Sentinel-2 / Landsat cloud-masked reference rasters
│   │   ├── hydrology/                  # BWDB river stage CSV records
│   │   ├── terrain/                    # DEM & HAND elevation models
│   │   └── event_documents/            # NDRCC / UN OCHA disaster situation reports
│   ├── processed/
│   │   ├── aligned/                    # Phase 1 harmonized GeoTIFFs (June 10, July 16)
│   │   ├── phase2a/                    # Phase 2A dB rasters & difference maps
│   │   ├── phase2b/                    # Phase 2B Lee 3x3, Lee 5x5 & quality masks
│   │   ├── phase3a/                    # Phase 3A candidate water masks
│   │   ├── phase3a_qc/                 # Phase 3A.1 corrected candidate water masks (36 GeoTIFFs)
│   │   ├── phase3b/                    # Phase 3B transition rasters & GeoJSON
│   │   └── phase3b_qc/                 # Phase 3B.1 certified transition rasters & GeoJSON
│   ├── outputs/
│   │   ├── phase2a/                    # Phase 2A histograms, QC CSVs
│   │   ├── phase2b/                    # Phase 2B ENL and edge preservation CSVs
│   │   ├── phase3a/                    # Phase 3A benchmark CSVs and figures
│   │   ├── phase3a_qc/                 # Phase 3A.1 corrected benchmark CSVs
│   │   ├── phase3b/                    # Phase 3B maps and statistics CSVs
│   │   └── phase3b_qc/                 # Phase 3B.1 certified summary CSVs
│   └── metadata/
│       ├── reference_data_registry.json
│       ├── phase4a_validation_readiness.json
│       ├── phase3b_qc_report.json / .md
│       ├── phase3b_change_detection_report.json / .md
│       ├── phase3a_qc_report.json / .md
│       ├── phase2b_final_review.json / .md
│       ├── reference_data_registry.json     # Phase 4B/4C.1 Provenance Registry (READY)
│       ├── phase4c1_sentinel2_ingestion_report.json # Phase 4C.1 metadata report
│       └── earth_pulse_project_state.json
├── docs/
│   ├── PHASE4A_VALIDATION_PROTOCOL.md   # Phase 4A independent validation protocol
│   ├── PHASE4B_SCIENTIFIC_CORRECTION_REPORT.md # Phase 4B.1 scientific corrections
│   ├── PHASE4C1_SENTINEL2_INGESTION_REPORT.md  # Phase 4C.1 Sentinel-2 ingestion report
│   ├── EARTH_PULSE_PROJECT_HANDOFF_2026-10-31.md # Historical Phase 2B handoff
│   └── EARTH_PULSE_PROJECT_HANDOFF_2026-11-01.md # CURRENT MASTER HANDOFF
├── scripts/
│   ├── align_sar_rasters.py            # Phase 1
│   ├── analyze_backscatter_phase2a.py   # Phase 2A
│   ├── quality_check_phase2a.py        # Phase 2A.1
│   ├── verify_scientific_corrections.py# Phase 2A.2
│   ├── filter_sar_phase2b.py           # Phase 2B
│   ├── classify_water_phase3a.py       # Phase 3A
│   ├── audit_phase3a.py                # Phase 3A.1
│   ├── detect_flood_change_phase3b.py  # Phase 3B
│   ├── audit_phase3b_qc.py             # Phase 3B.1
│   ├── validate_reference_data.py      # Phase 4A
│   ├── validate_reference_inputs.py    # Phase 4B / 4B.1
│   ├── ingest_reference_data.py        # Phase 4B / 4B.1
│   └── ingest_sentinel2_real.py        # Phase 4C.1
└── tests/
    └── test_*.py                       # 14 test files (153 unit tests total)
```

---

## 7. Outstanding Scientific Limitations

1. **Temporal Non-Simultaneity of Optical Reference:** June 07 optical vs June 10 SAR has a $\Delta t = 3\text{ days}$; July 17 optical vs July 16 SAR has a $\Delta t = 1\text{ day}$. River stage changes during these intervals must be accounted for during validation.
2. **Monsoon Cloud Occlusion in July Reference:** July 17 Sentinel-2 has $84.97\%$ cloud cover within the AOI, leaving $14.82\%$ clear pixels for validation. Validation metrics must be computed strictly on the clear-sky domain.
3. **Terrain Canopy Overestimation in GLO-30 DSM:** Because GLO-30 is a surface model, bare-earth floodplain elevations cannot be determined directly without hydrologic conditioning.
4. **PWD Vertical Datum Transformation Benchmark:** An authoritative, surveyed geodetic transformation connecting BWDB PWD to the EGM2008 geoid for Sirajganj/Kazipur reaches remains an external requirement before 3D water surface profiling can occur.

---

## 8. Exact Next Operational Tasks

When development resumes for the next milestone:
1. **Execute Phase 4D (Independent Reference Validation):**
   - Run pixel-level independent validation comparing the Phase 3B primary candidate water masks against the June 07 and July 17 reference water masks over clear, cloud-free pixels.
   - Compute independent 2x2 Confusion Matrix, Precision, Recall, F1-score, and IoU.
   - Evaluate spatial agreement patterns along the Jamuna braided channels vs terrestrial agricultural areas.
2. **Verify Test Suite:**
   - Run `python3 -m pytest -q tests/` to verify that all 153 unit tests continue passing.

