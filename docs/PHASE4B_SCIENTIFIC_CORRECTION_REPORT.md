# EARTH PULSE — PHASE 4B.1: REFERENCE INGESTION SCIENTIFIC CORRECTIONS REPORT

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River Reach, Kazipur / Sirajganj Districts, Bangladesh  
**Target Reference Grid:** EPSG:32645 (WGS 84 / UTM zone 45N), 20.0 m pixel spacing, $1405 \times 1393$ cells  
**Date:** 01 November 2026  
**Status:** All Scientific Corrections Applied; Test Suite Expanded to 144 Passing Tests (0 Failures)

---

## 1. EXECUTIVE SUMMARY

Phase 4B.1 addresses critical scientific and technical refinements identified in the Phase 4B reference data ingestion framework. These corrections resolve potential ambiguities in:
1. **Sentinel-2 SCL Class Interpretation:** Disentangling dark-area pixels (Class 2) from cloud shadows (Class 3) and water (Class 6).
2. **Sentinel-2 Radiometric Scaling:** Enforcing dynamic per-band `BOA_ADD_OFFSET` and `QUANTIFICATION_VALUE` metadata verification across ESA Processing Baselines.
3. **Landsat Spatial Support & Saturation:** Preserving native 30 m resolution metadata, documenting resampling effects, and integrating `QA_RADSAT` radiometric saturation.
4. **Copernicus GLO-30 Terminology & Hydrological Limitations:** Reclassifying GLO-30 as a Digital Surface Model (DSM) and documenting tree canopy and structure biases.
5. **Hydrological Datum Safety & Range Checks:** Enforcing PWD / EGM2008 non-interchangeability, protecting raw observations, and replacing hardcoded range rejection with configurable plausibility warnings.

All corrections have been implemented non-destructively, preserving historical outputs from Phases 1 through 4B.

---

## 2. PREVIOUS VERSUS CORRECTED INTERPRETATIONS

| Component | Previous Phase 4B Implementation | Phase 4B.1 Corrected Scientific Implementation | Scientific Justification |
|---|---|---|---|
| **Sentinel-2 SCL Class 2** | Labeled "Cast Shadow" and grouped with generic cloud shadows. | Explicitly classified as **Dark Area Pixels** (Value 252). Separate from Class 3 cloud shadows. | In ESA Sen2Cor L2A, Class 2 represents dark surfaces (topographic shadows, dark soils, burned areas, deep water bodies). It is an uncertain dark observation, NOT automatically cloud shadow or water. |
| **Sentinel-2 SCL Class 3** | Grouped with Class 2. | Classified specifically as **Cloud Shadows** (Value 253). | Cloud shadows are physically linked to cloud geometry and must be tracked separately from topographic or surface darkness. |
| **Sentinel-2 SCL Class 0** | Treated as generic uncertainty. | Mapped strictly to **NoData** (Value 255). | Class 0 represents missing detector pixels or swath edges; it is not an atmospheric observation. |
| **S2 Reflectance Scaling** | Single scalar `boa_add_offset` default (-1000.0 or 0.0) without baseline validation. | **Dynamic per-band parsing** (`validate_sentinel2_scaling_metadata`). Requires explicit per-band offsets for Baseline $\ge 04.00$; defaults to 0.0 for $< 04.00$. Missing metadata fails validation. | ESA Sen2Cor Level-2A products after January 2022 (Baseline 04.00+) introduce per-band radiometric offsets. Universal hardcoded offsets violate radiometric accuracy. |
| **Landsat Resolution** | Resampled to 20 m SAR grid with risk of implying 20 m optical ground truth. | **Preserves native 30 m resolution metadata**. Explicitly documents spatial support mismatch, point spread function smoothing, and provides 60 m block aggregation. | Upsampling 30 m optical data to 20 m via bilinear interpolation creates spatial autocorrelation; it does NOT generate new 20 m optical details. |
| **Landsat Saturation** | QA_PIXEL only. | Incorporates **QA_RADSAT** to detect radiometric saturation in bands B3 (Green), B5 (NIR), and B6 (SWIR-1). | Saturation clips spectral reflectance peaks, corrupting MNDWI and AWEI calculations. |
| **Copernicus GLO-30** | Described as Copernicus GLO-30 DEM. | Reclassified as **Copernicus GLO-30 Digital Surface Model (DSM)**. Documents canopy (3–15 m) and structure biases; disclaims bare-earth HAND derivation. | GLO-30 is derived from TanDEM-X X-band InSAR, which reflects canopy top and buildings. Treating it as bare ground creates artificial dams across floodplain channels. |
| **BWDB River Gauges** | Generic hardcoded 0–60 m range check. | **Configurable station-specific plausibility warning** (`plausibility_range`). Preserves all raw observations unaltered. | Hardcoded bounds risk rejecting legitimate flood crests or lower-stage readings. Plausibility checks must warn without destroying raw source data. |
| **Vertical Datum Safety** | PWD datum noted but conversion protection informal. | **`DATUM_INCOMPATIBILITY_PROTECTION` enforced**. Rejects datasets mixing PWD and EGM2008 without surveyed transformation parameters. | PWD is Bangladesh's national levelling datum ($\approx +0.46$ m relative to MSL). PWD and EGM2008 are geodetically distinct and non-interchangeable. |

---

## 3. TEST SUITE EXPANSION & VERIFICATION

A dedicated test suite has been implemented in [`tests/test_phase4b_scientific_corrections.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4b_scientific_corrections.py):

| Test ID | Test Case Name | Scientific Focus | Result |
|---|---|---|---|
| 1 | `test_01_scl_class2_dark_area_interpretation` | Class 2 identified as Dark Area Pixels, not conflated with shadow or water | **PASS** |
| 2 | `test_02_scl_class3_cloud_shadow_interpretation` | Class 3 identified specifically as Cloud Shadows uncertainty | **PASS** |
| 3 | `test_03_scl_nodata_handling` | Class 0 mapped to NoData (255), distinct from atmospheric uncertainty | **PASS** |
| 4 | `test_04_per_band_boa_add_offset_parsing` | Per-band offset dictionary parsed for Baseline $\ge 04.00$ | **PASS** |
| 5 | `test_05_processing_baseline_compatibility` | Pre-04.00 (offset=0) vs Post-04.00 (offset=-1000) verification | **PASS** |
| 6 | `test_06_missing_reflectance_metadata_rejection`| Missing baseline or invalid quantification value triggers failure | **PASS** |
| 7 | `test_07_landsat_native_resolution_preservation` | Output metadata preserves native 30 m resolution and resampling notice | **PASS** |
| 8 | `test_08_landsat_qa_radsat_handling` | QA_RADSAT saturation in B3, B5, or B6 masks pixels as uncertain | **PASS** |
| 9 | `test_09_pwd_egm2008_incompatibility_protection`| Rejecting mixing of PWD and EGM2008 without surveyed geodetic shift | **PASS** |
| 10 | `test_10_configurable_gauge_plausibility_warnings`| Plausibility range emits non-fatal warnings without rejecting raw data | **PASS** |
| 11 | `test_11_preservation_of_raw_gauge_values` | Original raw water level values preserved unaltered in output CSV | **PASS** |
| 12 | `test_12_validation_spatial_support_compatibility`| 60 m block aggregation (3x3 SAR vs 2x2 Landsat) comparison protocol | **PASS** |

### Complete Repository Status
- `pytest -q tests/test_phase4b_scientific_corrections.py`: **12 passed** in 1.87s.
- `pytest -q tests/test_reference_ingestion.py`: **18 passed** in 1.19s.
- Full test suite (`pytest -q tests/`): **144 passed** in 14.92s across all 13 test modules. Zero regressions.

---

## 4. REMAINING SCIENTIFIC LIMITATIONS

1. **Absence of Local Ground Truth:** No authentic reference files have yet been deposited into `data/reference/`. Repository validation status remains defensive and transparent: **`BLOCKED`**.
2. **Optical Cloud Persistence during Monsoon:** Sentinel-2 and Landsat optical imagery during the July 2024 flood peak across Bangladesh frequently suffer from cloud contamination ($> 80\%$). Only clear or cloud-shadow-free char/channel sub-domains can be validated.
3. **Terrain Canopy Overestimation in GLO-30 DSM:** Because GLO-30 is a surface model, bare-earth floodplain elevations cannot be determined directly without external LiDAR or hydrologic conditioning.
4. **PWD Vertical Datum Transformation Benchmark:** An authoritative, surveyed geodetic transformation formula connecting BWDB PWD to the EGM2008 geoid or WGS 84 ellipsoid for the Sirajganj/Kazipur reaches remains an external requirement before 3D water surface profiling can occur.

---

## 5. EXACT MANUAL DATA REQUIREMENTS

As documented in [`docs/PHASE4B_MANUAL_DATA_ACQUISITION_GUIDE.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4B_MANUAL_DATA_ACQUISITION_GUIDE.md):
- **Sentinel-2 MSI Level-2A:** Tile `T45RXE`, June 05–10, 2024 and July 14–17, 2024 (B03, B08, B11, B12, SCL, `MTD_MSIL2A.xml`).
- **Landsat 8/9 Level-2:** Path 138 / Row 043, June–July 2024 (SR_B3, SR_B5, SR_B6, QA_PIXEL, QA_RADSAT).
- **BWDB / FFWC River Stage CSV:** Stations `SW46.9` (Sirajganj) and `SW46.9A` (Kazipur), June 01 – July 31, 2024.
- **Copernicus GLO-30 DSM:** Tile `Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif` (`N24_E089`).

---

## 6. NEXT DEVELOPMENT MILESTONE

- **Phase 5A: Terrain Conditioning and Drainage Network Modeling (HAND Engine):** Implement sink-filling, flow direction, flow accumulation, and synthetic drainage network extraction for the Jamuna study reach to support Height Above Nearest Drainage (HAND) calculation once the Copernicus DSM tile is provided. Alternatively, when authentic reference data files are manually placed in `data/reference/`, run `scripts/ingest_reference_data.py` to trigger full pixel-level validation in Phase 4A.

