# EARTH PULSE — PHASE 4C.1: SENTINEL-2 REAL DATA INGESTION REPORT
**NASA Space Apps Challenge 2026 — Dancing with the SARs**  
**Author:** Earth Pulse Geospatial Engineering & Remote Sensing Science Team  
**Date:** 2026-11-02  
**Study Area:** Jamuna River Reach, Kazipur & Sirajganj Districts, Bangladesh  
**Canonical Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Reference Grid:** EPSG:32645 (UTM Zone 45N), $20.0\text{ m}$ pixel resolution, $1405 \times 1393$ cells ($1,957,165\text{ pixels}$, $782.87\text{ km}^2$)  
**Milestone Completed:** Phase 4C.1 — Sentinel-2 Real Data Ingestion & Quality Assessment  

---

## 1. Executive Summary

Phase 4C.1 successfully integrates two real Sentinel-2 MSI Level-2A datasets into the Earth Pulse processing architecture:
1. **Pre-monsoon baseline epoch:** June 07, 2024 (paired with the June 10 Sentinel-1 SAR acquisition; $\Delta t = 3\text{ days}$).
2. **Peak monsoon surge epoch:** July 17, 2024 (paired with the July 16 Sentinel-1 SAR acquisition; $\Delta t = 1\text{ day}$).

Both datasets were processed directly from authentic Copernicus Sentinel-2 MSI Level-2A ZIP archives. The framework applied **selective SAFE extraction** (extracting only the 5 required spectral bands and XML metadata, avoiding $>10\text{ GB}$ of disk bloating), **area-weighted spatial resampling** to the canonical $20\text{ m}$ SAR grid, **Processing Baseline 05.10 radiometric calibration** with dynamic per-band `BOA_ADD_OFFSET` ($-1000$) and `BOA_QUANTIFICATION_VALUE` ($10000$), **continuous spectral indices computation** (MNDWI, AWEI_nsh), and **rigorous Scene Classification Layer (SCL) quality masking** adhering strictly to the Phase 4B.1 scientific corrections (isolating Class 2 Dark Area Pixels from Class 3 Cloud Shadows and Class 6 Water).

Within the $404.02\text{ km}^2$ ($1,010,039\text{ pixels}$) Kazipur study AOI:
- **June 07, 2024:** Exhibits **$55.78\%$ usable clear observations** ($563,408\text{ pixels}$), with $25.41\%$ clear open water ($256,636\text{ pixels}$, $102.65\text{ km}^2$) and $43.89\%$ cloud occlusion. Validated status: **`READY`** for independent spatial validation.
- **July 17, 2024:** Reflects severe monsoon cloud cover with **$84.97\%$ cloud occlusion** ($858,219\text{ pixels}$) and **$14.82\%$ usable clear observations** ($149,718\text{ pixels}$), including $9.81\%$ clear water ($99,131\text{ pixels}$, $39.65\text{ km}^2$). Validated status: **`PARTIALLY_USABLE`** (statistically valid for masked pixel-level validation on cloud-free pixels, but unsuitable for full-scene spatial extent mapping).

All generated datasets have been verified with cryptographic SHA-256 checksums, registered into the provenance registry [`data/metadata/reference_data_registry.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/reference_data_registry.json), and validated with **9 dedicated unit tests** (expanding the project suite to **153 passing unit tests**, 0 failures).

---

## 2. Input Datasets & Cryptographic Provenance

Both datasets were acquired from the European Space Agency (ESA) via the Copernicus Data Space Ecosystem (CDSE) under Open Access terms.

| Property | June 07, 2024 Acquisition | July 17, 2024 Acquisition |
| :--- | :--- | :--- |
| **Archive Filename** | `S2A_MSIL2A_20240607T043711_N0510_R033_T45RYH_20240607T091101.SAFE.zip` | `S2A_MSIL2A_20240717T043701_N0510_R033_T45RYH_20240717T145054.SAFE.zip` |
| **Local File Path** | `data/reference/optical/sentinel2/June_2024/` | `data/reference/optical/sentinel2/July_2024/` |
| **Archive File Size** | $1,173,071,607\text{ bytes}$ ($1.09\text{ GB}$) | $1,174,383,230\text{ bytes}$ ($1.09\text{ GB}$) |
| **Cryptographic SHA-256** | `e4d9ecd24029af5f370fb994c4676370ea5a2a208995edc625feb4db34b53192` | `705d2d667e5fe7693e8b5a818eb4ba232baed7bac4be9403645eb2d4437bead4` |
| **Satellite Platform** | Sentinel-2A (MSI sensor) | Sentinel-2A (MSI sensor) |
| **Processing Baseline** | `05.10` ($\ge 04.00$) | `05.10` ($\ge 04.00$) |
| **Product Type** | `S2MSI2A` (Level-2A BOA Surface Reflectance) | `S2MSI2A` (Level-2A BOA Surface Reflectance) |
| **MGRS Tile Identifier** | `T45RYH` | `T45RYH` |
| **Observation Timestamp** | `2024-06-07T04:37:11.024Z` | `2024-07-17T04:37:01.024Z` |
| **Datatrip ID** | `DS_2APS_20240607T091101_S20240607T044444` | `DS_2APS_20240717T145054_S20240717T044924` |
| **Scene Cloud Percentage** | $46.59\%$ | $60.45\%$ |
| **Paired SAR Acquisition** | June 10, 2024 ($12:05\text{ UTC}$) | July 16, 2024 ($12:05\text{ UTC}$) |
| **Temporal Delta ($\Delta t$)** | $+3\text{ days}$ | $+1\text{ day}$ |

---

## 3. Selective SAFE Extraction

Standard uncompressed Sentinel-2 Level-2A `.SAFE` directories require between $1.5\text{ GB}$ and $2.0\text{ GB}$ of storage per granule. Because the Earth Pulse validation workflow strictly utilizes Green (B03), NIR (B08), SWIR-1 (B11), SWIR-2 (B12), the Scene Classification Layer (SCL), and associated XML metadata, extracting the complete archive would introduce unnecessary disk bloat and I/O overhead.

The pipeline implements an automated selective extraction protocol using Python's `zipfile` module:
- Target destination directories:
  - `data/reference/optical/sentinel2/extracted/june_2024/`
  - `data/reference/optical/sentinel2/extracted/july_2024/`
- Only seven files per archive are extracted:
  1. `*B03_10m.jp2` (Band 3 Green, $10\text{ m}$ native resolution, $\sim 115\text{ MB}$)
  2. `*B08_10m.jp2` (Band 8 NIR, $10\text{ m}$ native resolution, $\sim 128\text{ MB}$)
  3. `*B11_20m.jp2` (Band 11 SWIR-1, $20\text{ m}$ native resolution, $\sim 33\text{ MB}$)
  4. `*B12_20m.jp2` (Band 12 SWIR-2, $20\text{ m}$ native resolution, $\sim 33\text{ MB}$)
  5. `*SCL_20m.jp2` (Scene Classification Layer, $20\text{ m}$ native resolution, $\sim 3\text{--}4.6\text{ MB}$)
  6. `MTD_TL.xml` (Tile/Granule Level Metadata, $\sim 465\text{ KB}$)
  7. `MTD_MSIL2A.xml` (Datastrip / Product Metadata, $\sim 55\text{ KB}$)

Total extracted disk volume is **$\sim 312\text{ MB}$ per acquisition** ($\sim 624\text{ MB}$ combined), achieving an **$85\%$ reduction in storage footprint** compared to full SAFE directory expansion.

---

## 4. Radiometric Calibration (Processing Baseline 05.10)

ESA introduced Processing Baseline `04.00` in January 2022 (and `05.10` in 2024), adding negative digital number offsets (`BOA_ADD_OFFSET`) to prevent truncation of negative surface reflectance values resulting from atmospheric correction over dark pixels (such as deep water and cloud shadows).

Direct parsing of `MTD_MSIL2A.xml` confirmed the active parameters for both June 07 and July 17:
- `BOA_QUANTIFICATION_VALUE`: $10000.0$
- `BOA_ADD_OFFSET`: $-1000.0$ for all spectral bands ($B01$ through $B12$)

Digital numbers ($\text{DN}$) were converted to Bottom-Of-Atmosphere ($\text{BOA}$) surface reflectance ($\rho$) using the exact formula:
$$\rho_{\text{band}} = \frac{\text{DN}_{\text{band}} + \text{BOA\_ADD\_OFFSET}}{\text{BOA\_QUANTIFICATION\_VALUE}} = \frac{\text{DN}_{\text{band}} - 1000.0}{10000.0}$$

Pixels where $\text{DN} == 0$ represent source NoData / out-of-swath observations and were strictly assigned $\text{NaN}$ (and mapped to NoData value $-9999.0$ in output GeoTIFFs).

---

## 5. Area-Weighted Spatial Alignment to Canonical SAR Grid

To ensure pixel-for-pixel mathematical equivalence with the Sentinel-1 SAR products generated in Phase 1 through Phase 3B, all optical bands were warped to the canonical SAR reference grid:
- **Spatial Reference System:** `EPSG:32645` (WGS 84 / UTM Zone 45N)
- **Pixel Spacing:** $20.0\text{ m} \times 20.0\text{ m}$
- **Dimensions:** $1405\text{ columns} \times 1393\text{ rows}$ ($1,957,165\text{ cells}$, $782.87\text{ km}^2$)
- **Geotransform:** `(754115.6463743874, 20.0, 0.0, 2744939.181560975, 0.0, -20.0)`

### Resampling Strategy:
1. **Continuous Reflectance Bands ($B03$, $B08$, $B11$, $B12$):**
   - Resampled using **Area-Weighted Averaging** (`gdal.GRA_Average`).
   - For $10\text{ m}$ bands ($B03$, $B08$), a $2 \times 2$ block of native $10\text{ m}$ sub-pixels is averaged into each $20\text{ m}$ cell. This preserves radiometric energy and avoids the high-frequency aliasing and pixel phase distortion introduced by nearest-neighbour sampling.
   - For native $20\text{ m}$ bands ($B11$, $B12$), area-weighted averaging handles sub-pixel grid offsets cleanly.
2. **Categorical Classification Layer ($SCL$):**
   - Resampled strictly using **Nearest-Neighbour** (`gdal.GRA_NearestNeighbour`), preserving discrete integer class values ($0$ through $11$) without artificial interpolation.

All warped rasters match the canonical SAR reference grid bit-for-bit with $0\text{ px}$ spatial shift.

---

## 6. Spectral Water Indices Formulation

Using the calibrated surface reflectance rasters, continuous water indices were derived:

### 1. Modified Normalized Difference Water Index (MNDWI) (Xu, 2006)
$$\text{MNDWI} = \frac{\rho_{\text{Green}} - \rho_{\text{SWIR1}}}{\rho_{\text{Green}} + \rho_{\text{SWIR1}}} = \frac{\rho_{B03} - \rho_{B11}}{\rho_{B03} + \rho_{B11}}$$
MNDWI suppresses built-up land and bare soil while strongly enhancing open water, which exhibits high green reflectance and near-zero SWIR-1 absorption. Output values are strictly constrained to $[-1.0, 1.0]$.

### 2. Automated Water Extraction Index — Non-Shadow (AWEI_nsh) (Feyisa et al., 2014)
$$\text{AWEI}_{\text{nsh}} = 4 \times (\rho_{\text{Green}} - \rho_{\text{SWIR1}}) - (0.25 \times \rho_{\text{NIR}} + 2.75 \times \rho_{\text{SWIR2}}) = 4 \times (\rho_{B03} - \rho_{B11}) - (0.25 \times \rho_{B08} + 2.75 \times \rho_{B12})$$
Positive $\text{AWEI}_{\text{nsh}}$ values reliably delineate water bodies while suppressing urban and bare soil false positives.

---

## 7. Scene Classification Layer (SCL) Quality Masking

Following the scientific corrections established in Phase 4B.1, the Sentinel-2 Scene Classification Layer was remapped into discrete operational quality masks:

| SCL Value | Native ESA SCL Label | Earth Pulse Classification | Quality Mask Assignment | Water Mask Code |
| :---: | :--- | :--- | :--- | :---: |
| **0** | No Data | Out of swath / NoData | `nodata_mask` | `255` |
| **1** | Saturated or Defective | Sensor defect / saturation | `invalid_defective_mask` | `251` |
| **2** | **Dark Area Pixels** | **Uncertain Dark Observation** | `dark_area_mask` | `252` |
| **3** | Cloud Shadows | Cloud Shadow Uncertainty | `shadow_mask` | `253` |
| **4** | Vegetation | Clear Valid Land Cover | `valid_mask` | `0` (Non-Water) |
| **5** | Not Vegetated | Clear Valid Land Cover | `valid_mask` | `0` (Non-Water) |
| **6** | Water | Clear Valid Water | `valid_mask` | `1` (Water) |
| **7** | Low Probability Cloud | Cloud Uncertainty | `cloud_mask` | `254` |
| **8** | Medium Probability Cloud | Cloud Uncertainty | `cloud_mask` | `254` |
| **9** | High Probability Cloud | Cloud Uncertainty | `cloud_mask` | `254` |
| **10** | Thin Cirrus | Cirrus Cloud Uncertainty | `cloud_mask` | `254` |
| **11** | Snow or Ice | Excluded Glacial/Cryospheric | `snow_ice_mask` | `250` |

### Key Scientific Protections Enforced:
1. **SCL Class 2 (Dark Area Pixels) Isolation:** Class 2 pixels are strictly preserved in [`s2_*_aligned_dark_mask.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/reference/optical/sentinel2/) and assigned category `252`. They are **never conflated with Class 3 cloud shadows or Class 6 water**.
2. **Definitive Ground Truth Segregation:** Only clear valid pixels (SCL classes 4, 5, 6) can be evaluated as reference water (`1`) or non-water (`0`). All cloudy, shadowed, or dark pixels are quarantined from the validation denominator.

---

## 8. Kazipur Study AOI Quality Assessment & Usability Benchmarks

The $404.02\text{ km}^2$ Kazipur study AOI polygon (`POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`) contains exactly **$1,010,039\text{ pixels}$** on the $20\text{ m}$ reference grid.

The complete comparative breakdown between June 07 and July 17 is detailed below:

| Metric / Parameter | June 07, 2024 Acquisition | July 17, 2024 Acquisition | Temporal Change / Note |
| :--- | :---: | :---: | :--- |
| **Acquisition Timestamp** | `2024-06-07T04:37:11Z` | `2024-07-17T04:37:01Z` | $+39.999\text{ days}$ elapsed |
| **Paired SAR Acquisition** | June 10, 2024 ($12:05\text{ UTC}$) | July 16, 2024 ($12:05\text{ UTC}$) | Canonical Phase 1–3B SAR dates |
| **Temporal Gap ($\Delta t$)** | $+3\text{ days}$ | $+1\text{ day}$ | Non-simultaneous observations |
| **Total AOI Pixels** | $1,010,039$ | $1,010,039$ | Identical benchmark extent |
| **AOI Swath Coverage** | **$100.00\%$** ($0\text{ NoData px}$) | **$100.00\%$** ($0\text{ NoData px}$) | Entire AOI falls within tile T45RYH |
| **Usable Clear Pixels (Classes 4–6)** | **$563,408\text{ px}$** | **$149,718\text{ px}$** | $-413,690\text{ px}$ due to monsoon cloud |
| **Usable Clear Fraction** | **$55.78\%$** | **$14.82\%$** | $-40.96\%$ clear loss |
| **Clear Water Pixels (Ref Class 1)** | **$256,636\text{ px}$** | **$99,131\text{ px}$** | Area under clear sky |
| **Clear Water Area** | **$102.6544\text{ km}^2$** | **$39.6524\text{ km}^2$** | Clear water fraction of AOI: $25.41\%$ vs $9.81\%$ |
| **Clear Non-Water Pixels (Ref Class 0)**| **$306,772\text{ px}$** | **$50,587\text{ px}$** | Terrestrial floodplain & char vegetation |
| **Clear Non-Water Area** | **$122.7088\text{ km}^2$** | **$20.2348\text{ km}^2$** | Clear land fraction of AOI: $30.37\%$ vs $5.01\%$ |
| **Cloud Occlusion (Classes 7–10)** | $443,275\text{ px}$ ($43.89\%$) | $858,219\text{ px}$ ($84.97\%$) | $+41.08\%$ monsoon cloud increase |
| **Cloud Shadow Occlusion (Class 3)** | $3,356\text{ px}$ ($0.33\%$) | $1,912\text{ px}$ ($0.19\%$) | Shadow fraction isolated |
| **Dark Area Pixels (Class 2)** | $0\text{ px}$ ($0.00\%$) | $190\text{ px}$ ($0.02\%$) | Quarantined from water mask |
| **Clear Water Mean MNDWI** | $+0.0917$ | $+0.1917$ | Strong positive water signature |
| **Clear Land Mean MNDWI** | $-0.2268$ | $-0.3293$ | Negative terrestrial signature |
| **Validation Readiness Status** | **`READY`** | **`PARTIALLY_USABLE`** | Governs validation eligibility |

### Usability Classification:
- **June 07, 2024 (`READY`):** Over $55\%$ of the study AOI is cloud-free. The main Jamuna braided channel, permanent secondary channels, and extensive chars are clearly visible with high contrast. This dataset provides a robust, scientifically defensible optical reference for the pre-monsoon baseline.
- **July 17, 2024 (`PARTIALLY_USABLE`):** Heavy monsoon convective cloud cover obscures $85\%$ of the AOI. However, **$149,718\text{ clear pixels}$** ($59.89\text{ km}^2$) remain unobstructed, including significant reaches of the western bank and southern floodplain. Under the Phase 4A validation protocol, these clear pixels are statistically valid for **masked pixel-level validation (Precision, Recall, F1)**, provided all cloud and shadow pixels are excluded from the comparison matrix.

---

## 9. Temporal Non-Simultaneity & Hydrological Dynamics

Because optical sensors cannot penetrate cloud cover, simultaneous SAR and optical observations during the South Asian summer monsoon are virtually nonexistent.

### Temporal Intervals:
- **Baseline Epoch:** June 07 (Optical) vs June 10 (SAR) $\rightarrow \Delta t = 3\text{ days}$.
- **Monsoon Surge Epoch:** July 16 (SAR) vs July 17 (Optical) $\rightarrow \Delta t = 1\text{ day}$.

### Scientific Caveats for Validation:
1. **River Stage Fluctuation:** In the Jamuna braided system, river stage changes of $0.5\text{--}1.0\text{ m}$ over 24 to 72 hours are common during flood rising limbs. Such stage changes cause rapid horizontal inundation of low-lying sandbars (chars) and agricultural floodplains.
2. **Ephemerality of Inundation:** Inundation boundaries observed on June 07 may differ slightly from June 10 due to continuous pre-monsoon discharge increase.
3. **Validation Interpretation:** Discrepancies between SAR and optical masks must be interpreted in light of the temporal gap ($\Delta t$). False positives and false negatives along channel fringes must not be attributed solely to algorithm error without considering hydrograph slope.

---

## 10. Generated File Assets & Data Registry

The Phase 4C.1 pipeline generated the following Deflate-compressed GeoTIFFs, JSON reports, and CSV statistics:

```
EarthPulse-SAR/
├── data/
│   ├── reference/optical/sentinel2/
│   │   ├── extracted/
│   │   │   ├── june_2024/   # 7 extracted files (B03, B08, B11, B12, SCL, 2 XMLs)
│   │   │   └── july_2024/   # 7 extracted files (B03, B08, B11, B12, SCL, 2 XMLs)
│   ├── processed/reference/optical/sentinel2/
│   │   ├── june_2024/
│   │   │   ├── s2_june07_aligned_b03_20m.tif     # Calibrated BOA Green reflectance
│   │   │   ├── s2_june07_aligned_b08_20m.tif     # Calibrated BOA NIR reflectance
│   │   │   ├── s2_june07_aligned_b11_20m.tif     # Calibrated BOA SWIR-1 reflectance
│   │   │   ├── s2_june07_aligned_b12_20m.tif     # Calibrated BOA SWIR-2 reflectance
│   │   │   ├── s2_june07_aligned_scl.tif         # Resampled 20m SCL categorical raster
│   │   │   ├── s2_june07_aligned_mndwi.tif       # Continuous MNDWI [-1, 1]
│   │   │   ├── s2_june07_aligned_awei_nsh.tif    # Continuous AWEI_nsh
│   │   │   ├── s2_june07_aligned_valid_mask.tif  # Byte clear mask (classes 4, 5, 6)
│   │   │   ├── s2_june07_aligned_cloud_mask.tif  # Byte cloud mask (classes 7, 8, 9, 10)
│   │   │   ├── s2_june07_aligned_shadow_mask.tif # Byte shadow mask (class 3)
│   │   │   ├── s2_june07_aligned_dark_mask.tif   # Byte dark area mask (class 2)
│   │   │   └── s2_june07_aligned_water_mask.tif  # Reference water mask (0, 1, 250-255)
│   │   └── july_2024/
│   │       ├── s2_july17_aligned_b03_20m.tif
│   │       ├── s2_july17_aligned_b08_20m.tif
│   │       ├── s2_july17_aligned_b11_20m.tif
│   │       ├── s2_july17_aligned_b12_20m.tif
│   │       ├── s2_july17_aligned_scl.tif
│   │       ├── s2_july17_aligned_mndwi.tif
│   │       ├── s2_july17_aligned_awei_nsh.tif
│   │       ├── s2_july17_aligned_valid_mask.tif
│   │       ├── s2_july17_aligned_cloud_mask.tif
│   │       ├── s2_july17_aligned_shadow_mask.tif
│   │       ├── s2_july17_aligned_dark_mask.tif
│   │       └── s2_july17_aligned_water_mask.tif
│   ├── outputs/phase4c1/statistics/
│   │   ├── sentinel2_june07_qc.json              # Granular June QC statistics
│   │   ├── sentinel2_july17_qc.json              # Granular July QC statistics
│   │   ├── sentinel2_ingestion_summary.json      # Pipeline execution summary
│   │   └── sentinel2_aoi_comparison.csv          # Side-by-side comparison table
│   └── metadata/
│       ├── reference_data_registry.json          # Formally registered with authentic citations
│       └── phase4c1_sentinel2_ingestion_report.json
```

---

## 11. Automated Test Suite Verification

Phase 4C.1 added [`tests/test_phase4c1_s2_ingestion.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4c1_s2_ingestion.py) containing 9 comprehensive unit tests:
1. `test_archive_checksums_and_existence`: Verifies original ZIP existence and SHA-256 hashes.
2. `test_archive_metadata_extraction`: Verifies Baseline 05.10, quantification 10000, per-band offset -1000.
3. `test_selective_extraction_contents`: Confirms exactly 7 designated files extracted per date.
4. `test_aligned_rasters_spatial_geometry`: Confirms 1405x1393, EPSG:32645, and geotransform match.
5. `test_radiometric_reflectance_ranges`: Confirms BOA reflectance values are physically bounded.
6. `test_spectral_indices_computation`: Confirms MNDWI $[-1, 1]$ and finite AWEI values.
7. `test_scl_quality_masks_segregation`: Confirms strict isolation of Dark Area (252), Shadow (253), Cloud (254), and Clear (0/1).
8. `test_aoi_quality_assessment_benchmarks`: Confirms 1,010,039 pixels, coverage %, and usability status.
9. `test_reference_registry_compliance`: Confirms registry provenance schema and anti-circular rules.

**Test Run Result:**
```
============================= test session starts ==============================
rootdir: /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR
collected 153 items

tests/test_phase1_alignment.py ..........                                [  6%]
tests/test_phase2a_backscatter.py .........                              [ 12%]
tests/test_phase2a_quality.py .....                                      [ 15%]
tests/test_phase2a_scientific_correction.py .....                        [ 18%]
tests/test_phase2b_filtering.py ..............                           [ 28%]
tests/test_phase3a_classification.py ............                        [ 35%]
tests/test_phase3a_qc.py ..............                                  [ 45%]
tests/test_phase3b_change_detection.py ...............                   [ 54%]
tests/test_phase3b_qc.py ..........                                      [ 61%]
tests/test_phase4a_provenance.py ........                                [ 66%]
tests/test_phase4a_validation.py ............                            [ 74%]
tests/test_phase4b_scientific_corrections.py ............                [ 82%]
tests/test_phase4c1_s2_ingestion.py .........                            [ 88%]
tests/test_reference_ingestion.py ..................                     [100%]

============================= 153 passed in 19.62s =============================
```

All 153 tests passed with zero failures.

---

## 12. Next Operational Steps: Phase 4D Validation Readiness

With the two real Sentinel-2 optical reference datasets fully ingested, calibrated, and registered:
1. **Proceed to Phase 4D (Independent Reference Validation Execution):**
   - Run pixel-level independent validation comparing the Phase 3B primary candidate water masks against the June 07 and July 17 reference water masks over clear, cloud-free pixels.
   - Compute independent Precision, Recall, F1-score, and Intersection-over-Union (IoU).
   - Evaluate spatial agreement patterns along the Jamuna braided channels vs terrestrial agricultural areas.
2. **Maintain Strict Anti-Circular Safeguards:**
   - Ensure SAR candidate masks never feed into the reference masks.
   - Quarantining cloudy and shadowed pixels from validation statistics ensures accuracy metrics are scientifically defensible.

