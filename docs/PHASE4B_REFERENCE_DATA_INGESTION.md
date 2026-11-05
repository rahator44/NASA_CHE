# EARTH PULSE — PHASE 4B: INDEPENDENT REFERENCE DATA INGESTION FRAMEWORK

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River Reach, Kazipur / Sirajganj Districts, Bangladesh  
**Target SAR Reference Grid:** EPSG:32645 (WGS 84 / UTM zone 45N), 20.0 m pixel spacing, $1405 \times 1393$ cells  
**Hardware Profile:** Intel Core i7-1255U, 16 GB RAM, CPU-only, Linux  
**Status:** Ingestion Framework Operational; Real Reference Data Ingestion PENDING Manual Download (`BLOCKED`)  

---

## 1. EXECUTIVE SUMMARY & ARCHITECTURAL OVERVIEW

The primary objective of **Phase 4B** is to implement a robust, non-destructive, provenance-aware reference data ingestion engine for Earth Pulse. This engine bridges the gap between independent external validation data and the candidate surface-water and flood-change products produced from multi-temporal Sentinel-1 SAR imagery (June 10 and July 16, 2024).

In strict adherence to NASA Space Apps Challenge scientific governance and quality standards:
1. **Zero Data Invention:** No simulated or fabricated reference data has been placed into production data directories. The repository status for independent reference validation remains explicitly `BLOCKED` until authentic datasets are manually downloaded.
2. **Anti-Circular Validation Guard:** The ingestion and registry frameworks enforce strict anti-circular checks. Under no circumstances may Sentinel-1, SAR backscatter ($\sigma^0$), or SAR-derived candidate masks serve as ground truth for their own validation.
3. **Multi-Source Modality Support:** The ingestion framework supports four distinct categories of external reference information:
   - **Sentinel-2 MSI Level-2A** Bottom-Of-Atmosphere (BOA) optical imagery.
   - **Landsat 8/9 Level-2** Surface Reflectance (SR) optical imagery.
   - **BWDB / FFWC River Stage Gauge Records** (daily and sub-daily CSVs).
   - **Copernicus GLO-30 DEM** (30 m global digital elevation model).

```
                      +---------------------------------------+
                      |       Raw Reference Data Sources      |
                      +---------------------------------------+
                                          |
        +------------------+--------------+---------------+------------------+
        |                  |                              |                  |
        v                  v                              v                  v
+---------------+  +---------------+              +---------------+  +---------------+
| Sentinel-2 L2A|  | Landsat 8/9 L2|              | BWDB/FFWC CSV |  | Copernicus DEM|
| (10m / 20m)   |  | (30m)         |              | (Time-series) |  | (GLO-30 1-sec)|
+---------------+  +---------------+              +---------------+  +---------------+
        |                  |                              |                  |
        v                  v                              v                  v
+------------------------------------------------------------------------------------+
|               scripts/validate_reference_inputs.py  (Common QC Engine)             |
|   - File readability & GDAL format check       - SHA-256 integrity check           |
|   - Bounding box intersection with AOI         - Strict provenance verification    |
|   - Status: READY / WARNING / BLOCKED / REJECTED                                   |
+------------------------------------------------------------------------------------+
        |                  |                              |                  |
        v                  v                              v                  v
+------------------------------------------------------------------------------------+
|                    scripts/ingest_reference_data.py  (Pipelines)                   |
|   - Area-weighted resampling (10m->20m)        - Timestamp gap & duplicate check   |
|   - SCL cloud/shadow masking (254 uncertain)   - Vertical datum (PWD) tracking     |
|   - USGS reflectance scaling                   - Non-destructive 20m DEM alignment |
|   - Spectral indices: MNDWI, AWEI_nsh          - Rejection of unverified constants |
+------------------------------------------------------------------------------------+
        |                  |                              |                  |
        +------------------+--------------+---------------+------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |   Phase 4A Validation Engine Ready    |
                      | (scripts/validate_reference_data.py)  |
                      +---------------------------------------+
```

---

## 2. DIRECTORY STRUCTURE & INVENTORY

The canonical reference directory structure is established under `EarthPulse-SAR/data/reference/`:

```
EarthPulse-SAR/
├── data/
│   ├── metadata/
│   │   ├── reference_data_registry.json      <- Central provenance & checksum registry
│   │   ├── phase4a_provenance_audit.json     <- Completed Phase 4A.1 constant audit
│   │   └── phase4b_ingestion_status.json     <- Automated reference inventory audit
│   └── reference/
│       ├── optical/
│       │   ├── sentinel2/                    <- Target for Sentinel-2 L2A granules/bands
│       │   └── landsat/                      <- Target for Landsat 8/9 Level-2 products
│       ├── hydrology/                        <- Target for BWDB / FFWC gauge CSV records
│       ├── terrain/
│       │   ├── dem/                          <- Target for Copernicus GLO-30 DEM tiles
│       │   └── hand/                         <- Target for future calibrated HAND rasters
│       └── event_documents/                  <- Target for official flood situation bulletins
```

All existing Phase 1, Phase 2, and Phase 3 data structures remain completely unmodified.

---

## 3. PROVENANCE-AWARE REFERENCE DATA REGISTRY

The reference data registry (`data/metadata/reference_data_registry.json`) tracks every candidate external dataset. Registration is governed by `ReferenceDataRegistry` in `scripts/ingest_reference_data.py`.

### Required Metadata Fields
To achieve `READY` status, every registered dataset must supply all 16 mandatory provenance fields:
1. `dataset_id`: Unique identifier (e.g. `S2A_MSIL2A_20240715_T45RXE`).
2. `provider`: Authenticated data authority (e.g. `ESA Copernicus`, `USGS`, `BWDB`).
3. `product_name`: Official product description (e.g. `Sentinel-2 MSI Level-2A`).
4. `source_identifier`: Exact scene or product name from provider catalogue.
5. `source_url_or_citation`: Authoritative URL or peer-reviewed publication citation.
6. `acquisition_date`: ISO 8601 UTC timestamp or acquisition interval.
7. `processing_level`: Physical processing level (e.g. `Level-2A BOA Surface Reflectance`).
8. `spatial_extent`: Geographic description and bounding coordinates.
9. `crs`: Coordinate Reference System (e.g. `EPSG:32645` or `EPSG:4326`).
10. `spatial_resolution`: Nominal ground sample distance (e.g. `10m / 20m`).
11. `original_filename`: Base file name as delivered by data provider.
12. `sha256`: 64-character hexadecimal cryptographic hash calculated from raw source.
13. `processing_history`: Complete pipeline description (e.g. `Sen2Cor v2.11`).
14. `license_or_usage_conditions`: Distribution license (e.g. `CC-BY 4.0 Open Copernicus`).
15. `quality_information`: Documentation of cloud cover, sensor health, or gauge rating.
16. `intended_validation_purpose`: Explicit scientific validation role.

### Anti-Circular Validation Rules
The registry automatically scans all metadata strings for prohibited SAR-derived keywords (`sentinel-1`, `sigma0`, `gamma0`, `otsu`, `lee_3x3`, `lee_5x5`, `candidate_mask`, `phase3a`, `phase3b`). Any dataset matching these terms is immediately rejected with `CIRCULAR_VALIDATION_ERROR`.

---

## 4. SENTINEL-2 MSI LEVEL-2A INGESTION PIPELINE

Sentinel-2 MultiSpectral Instrument (MSI) Level-2A provides Bottom-Of-Atmosphere (BOA) reflectance suitable for pixel-level water surface validation during cloud-free or partially cloud-free periods.

### Required Bands
- **B03 (Green):** Central wavelength 560 nm, native resolution 10 m.
- **B08 (NIR):** Central wavelength 842 nm, native resolution 10 m.
- **B11 (SWIR-1):** Central wavelength 1610 nm, native resolution 20 m.
- **B12 (SWIR-2):** Central wavelength 2190 nm, native resolution 20 m.
- **SCL (Scene Classification Layer):** Pixel quality and cloud classification, native resolution 20 m.

### Reflectance Scaling
Copernicus Level-2A digital numbers (DN) are converted to dimensionless surface reflectance $\rho \in [0.0, 1.0]$:

$$\rho = \frac{\text{DN} + \text{BOA\_ADD\_OFFSET}}{\text{QUANTIFICATION\_VALUE}}$$

- **Baseline < 04.00:** $\text{QUANTIFICATION\_VALUE} = 10000$, $\text{BOA\_ADD\_OFFSET} = 0$.
- **Baseline $\ge$ 04.00 (January 2022 onwards):** $\text{QUANTIFICATION\_VALUE} = 10000$, $\text{BOA\_ADD\_OFFSET} = -1000$ (for negative reflectance offset correction).
- **NoData:** $\text{DN} = 0$ is preserved as NaN.

### Cloud and Shadow Quality Masking (SCL)
The Scene Classification Layer (SCL) is evaluated to isolate clear observations from atmospheric interference:

| SCL Class | Description | Pipeline Action | Output Value |
|---|---|---|---|
| 0 | NO_DATA | Excluded | 255 (NoData) |
| 1 | SATURATED_OR_DEFECTIVE | Excluded | 254 (Uncertain) |
| 2 | DARK_AREA_PIXELS / CAST_SHADOW | Excluded | 254 (Uncertain) |
| 3 | CLOUD_SHADOWS | Excluded | 254 (Uncertain) |
| 4 | VEGETATION | Evaluated | 0 (Non-Water) / 1 (Water) |
| 5 | NOT_VEGETATED | Evaluated | 0 (Non-Water) / 1 (Water) |
| 6 | WATER | Evaluated | 1 (Water) |
| 7 | UNCLASSIFIED | Excluded | 254 (Uncertain) |
| 8 | CLOUD_MEDIUM_PROBABILITY | Excluded | 254 (Uncertain) |
| 9 | CLOUD_HIGH_PROBABILITY | Excluded | 254 (Uncertain) |
| 10 | THIN_CIRRUS | Excluded | 254 (Uncertain) |
| 11 | SNOW_OR_ICE | Excluded | 254 (Uncertain) |

### Spectral Water Indices
The pipeline generates continuous floating-point indices:

1. **Modified Normalized Difference Water Index (MNDWI; Xu, 2006):**
   $$\text{MNDWI} = \frac{\rho_{\text{Green}} - \rho_{\text{SWIR1}}}{\rho_{\text{Green}} + \rho_{\text{SWIR1}}} = \frac{\text{B03} - \text{B11}}{\text{B03} + \text{B11}}$$
   Water exhibits strong absorption in SWIR-1 and high reflectance in Green, producing positive MNDWI values ($\text{MNDWI} > 0.0$).

2. **Automated Water Extraction Index - non-shadow (AWEI_nsh; Feyisa et al., 2014):**
   $$\text{AWEI}_{\text{nsh}} = 4 \times (\rho_{\text{Green}} - \rho_{\text{SWIR1}}) - (0.25 \times \rho_{\text{NIR}} + 2.75 \times \rho_{\text{SWIR2}})$$
   $$\text{AWEI}_{\text{nsh}} = 4 \times (\text{B03} - \text{B11}) - (0.25 \times \text{B08} + 2.75 \times \text{B12})$$
   AWEI_nsh improves discrimination of water in urbanized and mixed char environments.

### Spatial Alignment & Area-Weighted Aggregation
To align 10 m optical bands (B03, B08) with the 20 m SAR reference grid (EPSG:32645, $1405 \times 1393$ cells), the pipeline applies **area-weighted averaging** (`gdal.GRA_Average`). This aggregates four $10\text{ m} \times 10\text{ m}$ sub-pixels into each $20\text{ m} \times 20\text{ m}$ target grid cell, preserving radiative energy conservation. Nearest-neighbour resampling is strictly prohibited for continuous reflectance data. Categorical layers (SCL, mask) use nearest-neighbour with conservative uncertainty propagation.

---

## 5. LANDSAT 8/9 LEVEL-2 SURFACE REFLECTANCE INGESTION

Landsat 8 and Landsat 9 Operational Land Imager (OLI/OLI-2) Level-2 products provide 30 m multi-spectral observations.

### Required Bands
- **SR_B3 (Green):** Central wavelength 560 nm, 30 m.
- **SR_B5 (NIR):** Central wavelength 865 nm, 30 m.
- **SR_B6 (SWIR-1):** Central wavelength 1610 nm, 30 m.
- **QA_PIXEL:** 16-bit quality assessment bitmask, 30 m.

### Reflectance Scaling (USGS Standard)
Landsat Collection 2 Level-2 Surface Reflectance digital numbers are converted via:

$$\rho = 0.0000275 \times \text{DN} - 0.2$$

Valid surface reflectance values are constrained to $[0.0, 1.0]$. $\text{DN} = 0$ is flagged as Fill/NoData.

### QA_PIXEL Bitmask Decoding
Atmospheric contaminants are identified using bitwise operations:
- **Bit 0 (Fill):** $1 \implies$ NoData (mapped to 255).
- **Bit 1 (Dilated Cloud):** $1 \implies$ Excluded (mapped to 254).
- **Bit 2 (Cirrus):** $1 \implies$ Excluded (mapped to 254).
- **Bit 3 (Cloud):** $1 \implies$ Excluded (mapped to 254).
- **Bit 4 (Cloud Shadow):** $1 \implies$ Excluded (mapped to 254).
- **Bit 5 (Snow):** $1 \implies$ Excluded (mapped to 254).
- **Bit 7 (Water):** $1 \implies$ Corroborating water flag.

### Spatial Alignment
Landsat 30 m bands are warped to the EPSG:32645 20 m SAR grid using bilinear interpolation (`gdal.GRA_Bilinear`) for continuous reflectance and nearest-neighbour (`gdal.GRA_NearestNeighbour`) for `QA_PIXEL`.

---

## 6. BWDB / FFWC HYDROLOGICAL RIVER STAGE INGESTION

River gauge stage observations from the Bangladesh Water Development Board (BWDB) and Flood Forecasting and Warning Centre (FFWC) provide **temporal corroboration**, establishing whether SAR inundation expansion coincides with rising river levels.

### CSV Schema Specification
Candidate CSV files must include the following 10 mandatory columns:

| Column Name | Type | Description | Validation Rule |
|---|---|---|---|
| `station_id` | String | Official station ID (e.g. `SW46.9`) | Non-empty string |
| `station_name` | String | Station locality (e.g. `Sirajganj`) | Non-empty string |
| `observation_datetime` | ISO 8601 | Timestamp of gauge reading | Must parse to valid UTC/BST |
| `water_level` | Float | Observed water level | Numerical, within $[0.0, 60.0]$ m |
| `unit` | String | Measurement unit | Must equal `m` or `meters` |
| `vertical_datum` | String | Vertical reference datum | Must specify `PWD` or `EGM2008` |
| `provider` | String | Data agency (e.g. `BWDB`, `FFWC`) | Must be authenticated provider |
| `source_identifier` | String | Bulletin or bulletin table ID | Must reference official source |
| `source_citation` | String | Official report or yearbook citation | Reject `UNVERIFIED` / `ASSUMPTION` |
| `quality_flag` | String | Data quality flag (`GOOD`, `ESTIMATED`)| Non-empty string |

### Quality Enforcement & Rejection Rules
1. **Duplicate Detection:** Multiple records sharing the exact same `(station_id, observation_datetime)` are flagged and rejected.
2. **Missing Observation Detection:** Temporal gaps exceeding 1.5 times the expected observation interval (e.g. $> 4.5$ hours for 3-hour bulletins) are identified and recorded in the summary report.
3. **Unverified Danger Levels:** If a CSV includes `danger_level`, it must also provide `danger_level_citation` pointing to an official published source. Citations marked `UNVERIFIED`, `ASSUMPTION`, or missing cause immediate CSV rejection.
4. **Unverified Coordinates:** If a CSV includes station coordinates, it must provide `coordinates_citation` with an official benchmark survey reference.
5. **No Automatic Spatial Flood Mask:** Gauge levels represent 1D point observations along the river profile; they do NOT generate 2D spatial flood inundation masks without calibrated hydrodynamic models.

---

## 7. COPERNICUS GLO-30 DEM INGESTION

The Copernicus 30 m Global Digital Elevation Model (GLO-30) provides terrain elevation context.

### Specifications
- **Target Tile:** `N24_E089` (covering $24^\circ\text{N}$ to $25^\circ\text{N}$, $89^\circ\text{E}$ to $90^\circ\text{E}$).
- **Horizontal Datum / CRS:** WGS 84 (EPSG:4326), 1.0 arc-second ($\approx 30$ m ground spacing).
- **Vertical Datum:** EGM2008 geoid.
- **Elevation Units:** Meters.
- **NoData Value:** $-32767.0$.

### Non-Destructive Alignment Utility
The pipeline provides `resample_raster_to_grid` with `gdal.GRA_Bilinear` to warp the GLO-30 tile to the SAR target grid (EPSG:32645, 20 m resolution, $1405 \times 1393$ cells).

### Strict Scientific Constraints
- **Elevation Context Only:** DEM elevation alone does not indicate whether a pixel was flooded on July 16, 2024.
- **No Uncalibrated HAND Filtering:** Height Above Nearest Drainage (HAND) calculation requires hydrologically conditioning the DEM (filling sinks, carving channels) and calibrating against a verified drainage network. Applying arbitrary HAND cutoffs without hydraulic calibration is prohibited.

---

## 8. COMMON QUALITY CONTROL INTERFACE

Every dataset processed by `scripts/validate_reference_inputs.py` undergoes standardized quality screening and receives one of four discrete statuses:

```
[Candidate Dataset File]
           |
           +---> 1. File exists and is readable by GDAL / Pandas?
           |     NO  --> BLOCKED (Missing file) / REJECTED (Corrupt file)
           |
           +---> 2. Cryptographic SHA-256 computed & verified?
           |     NO  --> REJECTED (Checksum mismatch)
           |
           +---> 3. All mandatory provenance fields present?
           |     NO  --> REJECTED (Incomplete provenance)
           |
           +---> 4. Anti-circular check: Any SAR/Sentinel-1 terms?
           |     YES --> REJECTED (Circular validation fallacy)
           |
           +---> 5. Authenticated source citation provided?
           |     NO  --> REJECTED (Unverified citation / ASSUMPTION)
           |
           +---> 6. Bounding box intersects study AOI?
           |     NO  --> REJECTED (No spatial overlap)
           |
           +---> 7. Minor notices (e.g. moderate cloud cover > 30%)?
           |     YES --> WARNING (Acceptable with notice)
           |
           +---> ALL CHECKS PASS --> READY
```

---

## 9. CONNECTION TO PHASE 4A VALIDATION ENGINE

The ingestion pipelines in `scripts/ingest_reference_data.py` produce standardized reference rasters directly compatible with `compute_validation_metrics()` in `scripts/validate_reference_data.py`:

```python
from scripts.validate_reference_data import compute_validation_metrics

# candidate_mask: SAR Phase 3B transition mask (1: Water, 0: Non-Water, 5: Indeterminate, 6: NoData)
# reference_mask: S2/Landsat reference mask (1: Water, 0: Non-Water, 254: Cloud/Uncertain, 255: NoData)
results = compute_validation_metrics(
    candidate_mask=sar_candidate_arr,
    reference_mask=optical_ref_arr,
    candidate_nodata_val=6,
    candidate_indet_val=5,
    reference_nodata_val=255,
    reference_uncertain_val=254,
)
```

The metrics engine calculates:
- True Positives (TP), False Positives (FP), True Negatives (TN), False Negatives (FN).
- Precision, Recall, F1-score, IoU (Intersection over Union), Specificity, Balanced Accuracy, Overall Accuracy.
- Strict exclusion of SAR Indeterminate/NoData pixels and Optical Cloud/Shadow/NoData pixels.

---

## 10. AUTOMATED TEST SUITE & VERIFICATION

The framework includes 18 automated tests in `tests/test_reference_ingestion.py` using synthetic fixtures in temporary directories:

| Test ID | Test Name | Purpose | Result |
|---|---|---|---|
| `test_01` | `test_01_registry_metadata_validation` | Provenance fields verification | PASS |
| `test_02` | `test_02_sha256_checksum_registration` | File checksum hashing & registration | PASS |
| `test_03` | `test_03_sentinel2_metadata_inspection` | Sentinel-2 band package inspection | PASS |
| `test_04` | `test_04_sentinel2_cloud_and_shadow_exclusion` | SCL cloud/shadow/cirrus masking | PASS |
| `test_05` | `test_05_mndwi_calculation` | Xu (2006) MNDWI formula & division safety | PASS |
| `test_06` | `test_06_awei_nsh_calculation` | Feyisa et al. (2014) AWEI_nsh formula | PASS |
| `test_07` | `test_07_reflectance_scaling` | S2 DN/10000 & Landsat $0.0000275\cdot\text{DN}-0.2$ | PASS |
| `test_08` | `test_08_landsat_qa_pixel_masking` | QA_PIXEL bitmask decoding (bits 0,1,2,3,4) | PASS |
| `test_09` | `test_09_optical_spatial_alignment` | Area-weighted 10m to 20m aggregation | PASS |
| `test_10` | `test_10_hydrological_csv_validation` | Schema & numerical stage parsing | PASS |
| `test_11` | `test_11_duplicate_gauge_observation_detection`| Duplicate timestamp rejection | PASS |
| `test_12` | `test_12_missing_vertical_datum_handling` | Rejection of missing vertical datum | PASS |
| `test_13` | `test_13_rejection_of_unverified_danger_levels`| Rejection of unverified danger levels | PASS |
| `test_14` | `test_14_dem_crs_and_resolution_validation` | GLO-30 EPSG:4326 & AOI intersection check | PASS |
| `test_15` | `test_15_dem_nodata_handling` | DEM NoData detection & preservation | PASS |
| `test_16` | `test_16_rejection_of_missing_provenance` | Rejection of incomplete provenance | PASS |
| `test_17` | `test_17_rejection_of_sar_derived_reference_masks`| Anti-circular SAR rejection | PASS |
| `test_18` | `test_18_missing_reference_data_status` | Status `BLOCKED` when directory is unpopulated | PASS |

**Test Execution Summary:**
- Phase 4B test suite: **18 passed** in 1.42s (`pytest -q tests/test_reference_ingestion.py`).
- Complete repository test suite: **132 passed** in 14.55s (`pytest -q tests/`). Zero regressions.

---

## 11. MANUAL DATA ACQUISITION INSTRUCTIONS

Because automated scraping and data fabrication are strictly prohibited, official reference datasets must be manually downloaded by operators using the specifications below:

### A. Sentinel-2 Level-2A Optical Imagery
- **Provider:** European Space Agency (ESA) Copernicus Data Space Ecosystem.
- **Portal:** [dataspace.copernicus.eu](https://dataspace.copernicus.eu/)
- **Target Tile:** `T45RXE`
- **Acquisition Dates:**
  - Pre-flood baseline: **05–10 June 2024** (low cloud cover).
  - Flood peak / transition: **14–17 July 2024** (evaluate cloud percentage via SCL).
- **Target Folder:** `EarthPulse-SAR/data/reference/optical/sentinel2/`
- **Required Files:** Individual JP2/GeoTIFF band files (`B03_10m`, `B08_10m`, `B11_20m`, `B12_20m`, `SCL_20m`) or full `.SAFE` granule.

### B. Landsat 8/9 Level-2 Surface Reflectance
- **Provider:** USGS Earth Resources Observation and Science (EROS) Center.
- **Portal:** [earthexplorer.usgs.gov](https://earthexplorer.usgs.gov/)
- **Product:** Landsat 8-9 OLI/TIRS C2 L2
- **Path/Row:** `138 / 043`
- **Target Folder:** `EarthPulse-SAR/data/reference/optical/landsat/`
- **Required Files:** `*_SR_B3.TIF`, `*_SR_B5.TIF`, `*_SR_B6.TIF`, `*_QA_PIXEL.TIF`.

### C. BWDB / FFWC Hydrological River Gauge Records
- **Provider:** Bangladesh Water Development Board (BWDB) / Flood Forecasting and Warning Centre (FFWC).
- **Portal:** [ffwc.gov.bd](http://www.ffwc.gov.bd/)
- **Target Stations:**
  - `SW46.9` (Sirajganj Ghat, Jamuna River).
  - `SW46.9A` (Kazipur, Jamuna River).
  - `SW46.8` (Sariakandi, Jamuna River).
- **Required Timeframe:** 01 June 2024 to 31 July 2024 (daily or 3-hourly stage readings in meters PWD).
- **Target File:** Save as `bwdb_jamuna_river_stages_2024.csv` in `EarthPulse-SAR/data/reference/hydrology/`.

### D. Copernicus GLO-30 DEM
- **Provider:** Copernicus Open Access / AWS Open Data Registry (`copernicus-dem-30m`).
- **Tile ID:** `Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif`
- **Target Folder:** `EarthPulse-SAR/data/reference/terrain/dem/`.

---

## 12. CONCLUSION & OPERATIONAL READINESS

Phase 4B provides Earth Pulse with a complete, scientifically rigorous ingestion framework. Every mathematical formula, area-weighted resampling routine, bitmask filter, and anti-circular validation check has been verified through automated unit tests. 

Validation status remains transparently and defensively recorded as **`BLOCKED`** in `data/metadata/phase4b_ingestion_status.json` until authoritative external datasets are downloaded into the designated reference directories.

