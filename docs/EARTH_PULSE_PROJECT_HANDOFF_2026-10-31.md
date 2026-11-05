# EARTH PULSE — COMPLETE PROJECT HANDOFF DOCUMENT
**Date:** 2026-10-31  
**Project:** NASA Space Apps Challenge 2026 — "Dancing with the SARs"  
**System:** Earth Pulse — Automated Satellite Radar Flood Monitoring  
**Target Study Area:** Jamuna River, Kazipur & Sirajganj Districts, Bangladesh  
**Current Milestone Completed:** Phase 2B (Adaptive SAR Speckle Filtering, Quantitative Evaluation & Final Quality Review)  
**Next Milestone Planned:** Phase 3 (Water Classification & Inundation Change Detection)  

---

## 1. Project Identity & Objective
Earth Pulse is developed for the NASA Space Apps Challenge 2026 challenge *"Dancing with the SARs"*. 

The objective is to establish an end-to-end, scientifically validated, CPU-efficient SAR remote sensing pipeline for detecting and quantifying monsoon flood inundation along the highly dynamic braided reach of the Jamuna River in Bangladesh. The initial study pairs two Sentinel-1A C-band Synthetic Aperture Radar (SAR) Ground Range Detected (GRD) acquisitions:
- **Baseline (Pre-Flood):** June 10, 2024
- **Event (Peak Flood):** July 16, 2024

---

## 2. Hardware & Software Environment
- **Operating System:** Linux (Ubuntu / Debian x86_64, Kernel 6.x)
- **CPU:** Intel Core i7-1255U (12th Generation, 10 Cores, 12 Threads)
- **Memory:** 16 GB Physical RAM (DDR4/5)
- **Execution Mode:** CPU-only (Strictly no GPU or CUDA dependencies)
- **Core Dependencies:** Python 3.12+, GDAL 3.8.4 (`osgeo.gdal`, `osgeo.osr`), NumPy 1.26+, SciPy 1.11+, Matplotlib 3.8+, Pytest.
- **Preprocessing Tool:** ESA SNAP 14.0.0 (used for initial Level-1 orbit application, thermal noise removal, calibration, and Range-Doppler terrain correction).

---

## 3. Original Satellite Data Inventory
Located in `data/raw/sentinel1/`:
1. `S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69.zip`
   - **Timestamp:** 2024-06-10T12:05:08Z
   - **Characteristics:** Relative Orbit 143, Track 143, Ascending Pass, IW swath mode, dual-polarization (VV + VH), 1.74 GB.
2. `S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511.zip`
   - **Timestamp:** 2024-07-16T12:05:07Z
   - **Characteristics:** Relative Orbit 143, Track 143, Ascending Pass, IW swath mode, dual-polarization (VV + VH), 1.04 GB.

---

## 4. Completed Processing History (Phases 0 through 2B)

### Phase 0: Project & Dataset Read-Only Audit
- Audited complete project directory, SNAP intermediate products (`.dim`), SAFE XML metadata, and system resources.
- Verified that original SAFE metadata had `thermalNoiseCorrectionPerformed = false`, confirming that SNAP applied thermal noise subtraction exactly once (no double-correction defect).

### Phase 1: Raster Grid Harmonization Engine
- **Script:** [`scripts/align_sar_rasters.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/align_sar_rasters.py) | **Tests:** [`tests/test_phase1_alignment.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase1_alignment.py) (10 tests)
- **Objective:** Reconcile differing raster dimensions ($1405 \times 1393$ vs $1406 \times 1393$) and subpixel origin offsets onto June 10 reference grid.
- **Outputs:** [`data/processed/aligned/june10_aligned.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/aligned/june10_aligned.tif), [`data/processed/aligned/july16_aligned.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/aligned/july16_aligned.tif).
- **Standards:** EPSG:32645 (UTM 45N), 20 m resolution, Float32, NoData = -9999.0. Verified band order: Band 1 = Sigma0_VH, Band 2 = Sigma0_VV.

### Phase 2A: Radiometric Analysis & Backscatter Characterization
- **Script:** [`scripts/analyze_backscatter_phase2a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/analyze_backscatter_phase2a.py) | **Tests:** [`tests/test_phase2a_backscatter.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_backscatter.py) (9 tests)
- **Objective:** Decibel conversion ($\sigma^0_{\text{dB}} = 10 \log_{10}(\sigma^0_{\text{linear}})$), statistical characterization, and temporal differencing ($\Delta = \text{July} - \text{June}$).
- **Outputs:** Decibel rasters (`june10_sigma0_{vh,vv}_db.tif`, `july16_sigma0_{vh,vv}_db.tif`) and difference rasters (`delta_{vh,vv}_db.tif`).
- **Discovery:** Identified anomalous extreme positive differences ($> +70\text{ dB}$, max $+91.5\text{ dB}$) and low values approaching $-105.9\text{ dB}$.

### Phase 2A.1: Quality Control & Anomaly Investigation
- **Script:** [`scripts/quality_check_phase2a.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/quality_check_phase2a.py) | **Tests:** [`tests/test_phase2a_quality.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_quality.py) (5 tests)
- **Objective:** Quantified low-backscatter bins ($< -20\text{ dB}$ down to $< -50\text{ dB}$), extracted Kazipur AOI statistics ($1,009,978$ common valid cells), and proved extreme differences are logarithmic division artifacts over noise-floor pixels.

### Phase 2A.2: Scientific Interpretation Correction
- **Script:** [`scripts/verify_scientific_corrections.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/verify_scientific_corrections.py) | **Tests:** [`tests/test_phase2a_scientific_correction.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2a_scientific_correction.py) (5 tests)
- **Objective:** Discovered the exact source of $\approx -105.9\text{ dB}$: SNAP's `ThermalNoiseRemovalOp` internal clipping constant ($I = 1.0 \times 10^{-5}$), which calibrates to $\sigma^0 = 10^{-5} / A_\sigma^2 \in [2.5538 \times 10^{-11}, 2.6459 \times 10^{-11}]$.
- **Key Retraction:** Retracted $-35\text{ dB}$ as an exact physical noise floor (nominal NESZ is $-22$ to $-28\text{ dB}$). Established four-tier radiometric framework and corrected classification guidance: sub-detection pixels are indeterminate, NOT confirmed water.

### Phase 2B: Adaptive SAR Speckle Filtering & Evaluation
- **Script:** [`scripts/filter_sar_phase2b.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/filter_sar_phase2b.py) | **Tests:** [`tests/test_phase2b_filtering.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase2b_filtering.py) (14 tests)
- **Objective:** Standard adaptive Lee speckle filtering ($3\times 3$ and $5\times 5$) strictly in linear power. Generated standalone quality masks isolating clipping-floor pixels.
- **Outputs:** Lee 3×3 GeoTIFFs, Lee 5×5 GeoTIFFs, Quality Mask GeoTIFFs, comparative figures, and CSV evaluation summaries.

---

## 5. Critical Scientific Foundations Established
1. **Band Ordering:** Band 1 is strictly `Sigma0_VH`; Band 2 is strictly `Sigma0_VV`.
2. **Filtering Domain:** Filtering must be performed in **linear power domain** ($\sigma^0_{\text{linear}}$), never decibels. Decibel filtering introduces a $-2.5\text{ dB}$ negative bias due to Jensen's inequality.
3. **Clamping Constant Reality:** Values near $-105.9\text{ dB}$ ($2.55 \times 10^{-11}$) are software intensity clamp artifacts ($I = 10^{-5}$), not physical ground measurements.
4. **Sub-Detection Is Indeterminate:** Observations below detection limits can arise from radar shadow, tarmac, dry planar sand, or border nulls. They must **never automatically be classified as water**.
5. **No Final Filter Monopoly:** Both Lee 3×3 and Lee 5×5, alongside Unfiltered data, are preserved for multi-scenario threshold evaluation in Phase 3.

---

## 6. Current Directory Tree (Important Deliverables)

```text
EarthPulse-SAR/
├── data/
│   ├── raw/sentinel1/                  # Original Level-1 GRD ZIP archives
│   ├── intermediate/                   # Original SNAP .dim / .data terrain-corrected products
│   ├── processed/
│   │   ├── aligned/                    # Phase 1 harmonized GeoTIFFs (June 10, July 16)
│   │   ├── phase2a/                    # Phase 2A dB rasters & difference maps
│   │   └── phase2b/
│   │       ├── quality_mask/           # SNAP clipping-floor quality masks (June 10, July 16)
│   │       ├── lee_3x3/                # Lee 3×3 filtered rasters (June 10, July 16)
│   │       └── lee_5x5/                # Lee 5×5 filtered rasters (June 10, July 16)
│   ├── outputs/
│   │   ├── phase2a/                    # Histograms, anomaly maps, and CSV tables
│   │   └── phase2b/
│   │       ├── comparisons/            # Visual tri-panel plots, histograms & transect plots
│   │       └── statistics/             # ENL gains and edge preservation CSVs
│   └── metadata/                       # Machine-readable JSON audits & state
│       ├── phase1_alignment_report.json
│       ├── phase2a_analysis_report.json
│       ├── phase2a_quality_report.json
│       ├── phase2a_scientific_correction_addendum.json
│       ├── phase2a_scientific_correction_addendum.md
│       ├── phase2b_filtering_report.json
│       ├── phase2b_edge_investigation.json
│       ├── phase2b_final_review.json
│       ├── phase2b_final_review.md
│       └── earth_pulse_project_state.json
├── docs/
│   └── EARTH_PULSE_PROJECT_HANDOFF_2026-10-31.md  <-- THIS HANDOFF DOCUMENT
├── scripts/
│   ├── __init__.py
│   ├── align_sar_rasters.py            # Phase 1 alignment engine
│   ├── analyze_backscatter_phase2a.py   # Phase 2A radiometric analysis engine
│   ├── quality_check_phase2a.py        # Phase 2A.1 quality check engine
│   ├── verify_scientific_corrections.py# Phase 2A.2 correction engine
│   ├── filter_sar_phase2b.py           # Phase 2B adaptive Lee filtering engine
│   └── review_phase2b_edges.py         # Phase 2B edge & transect review script
└── tests/
    ├── __init__.py
    ├── test_phase1_alignment.py        # 10 unit tests
    ├── test_phase2a_backscatter.py      # 9 unit tests
    ├── test_phase2a_quality.py          # 5 unit tests
    ├── test_phase2a_scientific_correction.py # 5 unit tests
    └── test_phase2b_filtering.py        # 14 unit tests
```

---

## 7. Current Output Checksum Inventory

All files verified intact as of 2026-10-31:
- `june10_aligned.tif` (9,410,940 bytes) | SHA-256: `c54f97e0a24b20574f38c786ac82e38855c266a5842c7f099d980d6b239f9252`
- `july16_aligned.tif` (9,283,566 bytes) | SHA-256: `7b441b2a8a816dcc35b1e64b828def155687658e27be357ddb2e43984099c353`
- `june10_sigma0_vh_db.tif` (4,320,826 bytes) | SHA-256: `c1c95ac3537840a5fef39eaa34184b0c0e20151bb06bd731d9fafa3ee2f2d76c`
- `june10_sigma0_vv_db.tif` (4,571,642 bytes) | SHA-256: `c5256db594a8cf49976fde20bdf65582153ea118939fa835b162dbb5f3ced8f4`
- `july16_sigma0_vh_db.tif` (4,301,386 bytes) | SHA-256: `0a9915cea8a25317e29d4cff6f78fcb4972bf56ebaecd06c58e406c5f839985e`
- `july16_sigma0_vv_db.tif` (4,479,316 bytes) | SHA-256: `8717fb72e58828ba568552a044eb85bb562d2cac68d0c9b728ebdf3a234443c8`
- `delta_vh_db.tif` (4,995,406 bytes) | SHA-256: `52377b47484191c3fa57aafcce0523f55fef62ef717fdcb8fee63bb19636817b`
- `delta_vv_db.tif` (4,961,242 bytes) | SHA-256: `74f0f5aaa43e8f3ef754e9eb9441e72c9ad22c6524da52b88c0b552cc901ef87`
- `june10_lee_3x3.tif` (20,430,254 bytes) | SHA-256: `6e922082fb6838d783e1449b2aa13df922056abe670d41865d1431d254c64f12`
- `july16_lee_3x3.tif` (20,668,700 bytes) | SHA-256: `bbd91a0655267d7877e92d8324199fba69c88d653f21a6e0edde06a3f68fcb65`
- `june10_lee_5x5.tif` (20,325,358 bytes) | SHA-256: `1479ce3fdb415b253a940f1a0babaac552cb079c279abc785007ed9c6deb5215`
- `july16_lee_5x5.tif` (20,622,122 bytes) | SHA-256: `933c39c844cc84260d33fc67c452d3cab38e001b8be4d4b77c7b10c7858aa140`
- `june10_quality_mask.tif` (57,918 bytes) | SHA-256: `441e4c1bf6ec343f268077d3dcee6968822fed741857c266bde315a0610f480c`
- `july16_quality_mask.tif` (36,412 bytes) | SHA-256: `bd83f9feef19f3cde7b6c29c1e951a0978864eba9823247ccbaa0b63be7b3a36`

---

## 8. Test Suite Status
- **Total Test Cases:** **43 passing tests** (100% passing rate in $pprox 12.6$ seconds).
- **Test Command:** `python3 -m pytest -q tests/`
- **Breakdown:**
  - `test_phase1_alignment.py`: 10 passed
  - `test_phase2a_backscatter.py`: 9 passed
  - `test_phase2a_quality.py`: 5 passed
  - `test_phase2a_scientific_correction.py`: 5 passed
  - `test_phase2b_filtering.py`: 14 passed

---

## 9. Outstanding Scientific Limitations
1. **Lack of Independent In-Situ Ground Truth:** No gauge water-level or synchronous optical (Sentinel-2 / Landsat) cloud-free masks are currently ingested to provide external F1-score validation.
2. **Unavailability of Orthorectified Noise Vector:** Exact per-pixel detection limits are mathematically absent from the UTM rasters because SNAP discarded the noise band (`outputNoise = false`).
3. **Subpixel Co-Registration Margin:** July 16 was aligned via bilinear resampling to the June 10 grid; localized subpixel displacement errors ($< 0.25$ pixels) remain inherent.
4. **Two-Epoch Baseline:** Only two dates are currently processed (36-day gap); intra-seasonal flood rise and recession dynamics require additional Sentinel-1 scenes.

---

## 10. Next Milestone Roadmap: Phase 3 (Water Classification & Change Detection)
When Phase 3 commences, the developer must implement:
1. **Comparative Thresholding:** Evaluate automated thresholding (Otsu, Bivariate, Kittler-Illingworth) across **Unfiltered**, **Lee 3×3**, and **Lee 5×5** datasets.
2. **Polarization Fusion:** Test VV-only, VH-only, and dual-polarization cross-ratio ($	ext{CR} = \sigma^0_{	ext{VH}} / \sigma^0_{	ext{VV}}$) thresholding.
3. **Topological Masking:** Ingest Elevation / Height Above Nearest Drainage (HAND) or slope masks to eliminate terrain shadow false positives.
4. **Indeterminate Pixel Segregation:** Handle Category 2 (clipping floor) pixels using contextual / multi-temporal voting rather than blanket water labeling.
5. **Change Classification:** Separate:
   - Persistent Water (present in June and July)
   - Newly Inundated Land (flood expansion)
   - Receded / Evaporated Water (drydown)
   - Persistent Non-Water (unflooded land)
6. **Acreage & Hectare Quantification:** Compute surface water areas inside the Kazipur study AOI with formal uncertainty margins.

---

## 11. Instructions for Starting Tomorrow

### 1. Environment Verification
```bash
cd /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR
python3 -m pytest -q tests/
```
Verify that all 43 tests pass.

### 2. Primary Datasets to Ingest for Phase 3
Use the verified Level-2 filtered rasters:
- `data/processed/phase2b/lee_5x5/june10_lee_5x5.tif`
- `data/processed/phase2b/lee_5x5/july16_lee_5x5.tif`
- `data/processed/phase2b/quality_mask/june10_quality_mask.tif`
- `data/processed/phase2b/quality_mask/july16_quality_mask.tif`
Also retain `lee_3x3/` and `aligned/` for the required three-way sensitivity benchmark.

### 3. Golden Scientific Rules to Maintain
- Never convert linear Sigma0 to dB prior to spatial filtering.
- Never label pixels below detection limits as confirmed water.
- Never overwrite previous phase deliverables.
- Always enforce NoData = -9999.0 and EPSG:32645.
