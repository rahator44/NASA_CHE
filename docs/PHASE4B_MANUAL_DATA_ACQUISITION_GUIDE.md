# EARTH PULSE — PHASE 4B: MANUAL REFERENCE DATA ACQUISITION GUIDE

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River Reach, Kazipur / Sirajganj Districts, Bangladesh  
**Target Reference Grid:** EPSG:32645 (WGS 84 / UTM zone 45N), 20.0 m pixel spacing, $1405 \times 1393$ cells  
**Policy Restriction:** Direct automated scraping or synthetic data fabrication in production folders is **STRICTLY PROHIBITED**. Independent reference datasets must be manually acquired by authorized operators from official repositories and verified through the quality control framework.

---

## 1. ACQUISITION OVERVIEW & TARGET MATRIX

| Modality | Data Provider | Platform / Collection | Temporal Window | Spatial Footprint | Primary Validation Purpose |
|---|---|---|---|---|---|
| **Optical (Primary)** | ESA / Copernicus | Sentinel-2 MSI Level-2A (BOA) | June 05–10, 2024 & July 14–17, 2024 | Tile `T45RXE` | 10m/20m pixel-level reference water mask (MNDWI / AWEI) |
| **Optical (Secondary)** | USGS / NASA | Landsat 8/9 OLI/TIRS C2 L2 (SR) | June 01–July 31, 2024 | Path 138 / Row 043 | 30m multi-spectral reference water cross-check |
| **Hydrology** | BWDB / FFWC | River Stage Gauge Bulletins | June 01–July 31, 2024 (Daily / 3-hr) | Sirajganj (`SW46.9`), Kazipur (`SW46.9A`) | River stage rise/fall temporal corroboration |
| **Terrain (Surface)** | ESA / Copernicus | Copernicus GLO-30 DSM | Baseline Global Release | Tile `N24_E089` | 30m surface elevation & canopy context |

---

## 2. SENTINEL-2 MSI LEVEL-2A OPTICAL IMAGERY

### A. Data Authority & Access Portal
- **Authority:** European Space Agency (ESA) Copernicus Programme.
- **Access Portal:** [Copernicus Data Space Ecosystem (CDSE)](https://dataspace.copernicus.eu/)
- **Product Type:** `S2MSI2A` (Level-2A Bottom-Of-Atmosphere reflectance).
- **Target MGRS Tile:** `T45RXE` (subject to exact footprint verification covering Kazipur and Sirajganj).

### B. Target Temporal Windows
1. **Pre-Flood Baseline Acquisition:** Target 05 June – 10 June 2024 (minimizing cloud cover; temporally proximate to Sentinel-1 acquisition of 10 June 2024 12:12 UTC).
2. **Flood Transition / Peak Acquisition:** Target 14 July – 17 July 2024 (evaluating cloud cover; temporally proximate to Sentinel-1 acquisition of 16 July 2024 12:12 UTC).

### C. Required Files & Directory Destination
Destination Directory:
`EarthPulse-SAR/data/reference/optical/sentinel2/`

Required Component Files (per acquisition granule):
- `*_B03_10m.jp2` or `.tif`: Band 3 Green (560 nm, 10 m).
- `*_B08_10m.jp2` or `.tif`: Band 8 NIR (842 nm, 10 m).
- `*_B11_20m.jp2` or `.tif`: Band 11 SWIR-1 (1610 nm, 20 m).
- `*_B12_20m.jp2` or `.tif`: Band 12 SWIR-2 (2190 nm, 20 m).
- `*_SCL_20m.jp2` or `.tif`: Scene Classification Layer (20 m).
- `MTD_MSIL2A.xml`: Granule / product metadata XML (containing `PROCESSING_BASELINE`, `QUANTIFICATION_VALUE`, and per-band `BOA_ADD_OFFSET` table).

### D. Minimum Metadata & Provenance Requirements
Operators must record or extract into `metadata.json`:
- `dataset_id`: e.g. `S2A_MSIL2A_20240715T043701_T45RXE`
- `provider`: `ESA Copernicus`
- `product_name`: `Sentinel-2A MSI Level-2A`
- `processing_baseline`: e.g. `05.10` or `04.00`
- `quantification_value`: `10000.0`
- `boa_add_offsets`: Per-band dictionary (e.g. `{"B03": -1000.0, "B08": -1000.0, "B11": -1000.0, "B12": -1000.0}`)
- `cloud_coverage_percentage`: Must be $< 40\%$ across the Jamuna AOI.

### E. Acceptance Checks
Run quality verification prior to ingestion:
```bash
python3 -c "
from scripts.validate_reference_inputs import validate_sentinel2_optical
bands = {
    'B03': 'data/reference/optical/sentinel2/B03.tif',
    'B08': 'data/reference/optical/sentinel2/B08.tif',
    'B11': 'data/reference/optical/sentinel2/B11.tif',
    'B12': 'data/reference/optical/sentinel2/B12.tif',
    'SCL': 'data/reference/optical/sentinel2/SCL.tif',
}
res = validate_sentinel2_optical(bands)
print('Status:', res.status)
assert res.status in ['READY', 'WARNING'], res.errors
"
```

### F. Expected Ingestion Command
```bash
python3 -c "
from scripts.ingest_reference_data import ingest_sentinel2_l2a
bands = { ... }
meta = { ... }
ingest_sentinel2_l2a(bands, output_dir='data/processed/reference/sentinel2_july15', metadata=meta)
"
```

---

## 3. LANDSAT 8/9 LEVEL-2 SURFACE REFLECTANCE

### A. Data Authority & Access Portal
- **Authority:** U.S. Geological Survey (USGS) Earth Resources Observation and Science (EROS) Center.
- **Access Portal:** [USGS EarthExplorer](https://earthexplorer.usgs.gov/) or [USGS Machine-to-Machine (M2M) API](https://m2m.cr.usgs.gov/).
- **Collection / Level:** Landsat Collection 2 Level-2 Surface Reflectance (L2SP).
- **Target WRS-2 Path/Row:** `Path 138 / Row 043` (subject to exact footprint verification).

### B. Required Files & Directory Destination
Destination Directory:
`EarthPulse-SAR/data/reference/optical/landsat/`

Required Component GeoTIFFs:
- `*_SR_B3.TIF`: Surface Reflectance Band 3 (Green, 30 m native).
- `*_SR_B5.TIF`: Surface Reflectance Band 5 (NIR, 30 m native).
- `*_SR_B6.TIF`: Surface Reflectance Band 6 (SWIR-1, 30 m native).
- `*_QA_PIXEL.TIF`: Pixel Quality Assessment bitmask (30 m native).
- `*_QA_RADSAT.TIF`: Radiometric Saturation and Occlusion bitmask (30 m native).
- `*_MTL.json` or `.txt`: Product metadata file.

### C. Minimum Metadata & Provenance Requirements
- `dataset_id`: e.g. `LC09_L2SP_138043_20240716_20240718_02_T1`
- `provider`: `USGS / NASA`
- `product_name`: `Landsat 9 OLI-2 Level-2 Surface Reflectance`
- `native_spatial_resolution_m`: `30.0`
- `scale_factor`: `0.0000275`
- `add_offset`: `-0.2`
- `spatial_support_notice`: Note that bilinear resampling to 20m does NOT increase spatial resolution.

### D. Acceptance Checks
```bash
python3 -c "
from scripts.validate_reference_inputs import validate_landsat_optical
bands = {
    'SR_B3': 'data/reference/optical/landsat/SR_B3.TIF',
    'SR_B5': 'data/reference/optical/landsat/SR_B5.TIF',
    'SR_B6': 'data/reference/optical/landsat/SR_B6.TIF',
    'QA_PIXEL': 'data/reference/optical/landsat/QA_PIXEL.TIF',
    'QA_RADSAT': 'data/reference/optical/landsat/QA_RADSAT.TIF',
}
res = validate_landsat_optical(bands)
print('Status:', res.status)
assert res.status in ['READY', 'WARNING'], res.errors
"
```

### E. Expected Ingestion Command
```bash
python3 -c "
from scripts.ingest_reference_data import ingest_landsat_l2
bands = { ... }
ingest_landsat_l2(bands, output_dir='data/processed/reference/landsat_july16')
"
```

---

## 4. BWDB / FFWC HYDROLOGICAL RIVER STAGE DATA

### A. Data Authority & Access Portal
- **Authority:** Bangladesh Water Development Board (BWDB) Hydrology Directorate & Flood Forecasting and Warning Centre (FFWC).
- **Access Portal:** [FFWC Daily Flood Bulletins](http://www.ffwc.gov.bd/) & BWDB Hydrology Yearbooks.
- **Target Stations:**
  - `SW46.9` (Sirajganj Ghat, Jamuna River).
  - `SW46.9A` (Kazipur, Jamuna River).
  - `SW46.8` (Sariakandi, Jamuna River).
- **Target Period:** 01 June 2024 to 31 July 2024.

### B. Required File Schema & Destination
Destination Directory:
`EarthPulse-SAR/data/reference/hydrology/`  
Target Filename: `bwdb_jamuna_river_stages_2024.csv`

Mandatory 10-Column Schema:
```csv
station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag
SW46.9,Sirajganj,2024-06-10T06:00:00Z,10.82,m,PWD,BWDB,FFWC-BULLETIN-20240610,BWDB Hydrology Directorate Daily Bulletin 2024,GOOD
SW46.9,Sirajganj,2024-07-16T06:00:00Z,14.15,m,PWD,BWDB,FFWC-BULLETIN-20240716,BWDB Hydrology Directorate Daily Bulletin 2024,GOOD
```

### C. Datum & Plausibility Governance Rules
1. **Vertical Datum Mandatory:** Must be explicitly specified as `PWD` (Public Works Datum).
2. **No Uncalibrated Conversions:** PWD must NOT be converted to MSL or EGM2008 without surveyed bench-mark transformation parameters.
3. **Danger Levels & Coordinates:** Must NOT be included unless accompanied by official citations (`danger_level_citation`, `coordinates_citation`).
4. **Plausibility:** Plausibility range for Jamuna at Sirajganj/Kazipur is approximately $5.0\text{ m}$ to $20.0\text{ m}$ PWD. Readings outside this range emit non-fatal warnings but preserve original raw observations.

### D. Acceptance Checks
```bash
python3 -c "
from scripts.validate_reference_inputs import validate_hydrological_csv
res = validate_hydrological_csv('data/reference/hydrology/bwdb_jamuna_river_stages_2024.csv')
print('Status:', res.status)
assert res.status in ['READY', 'WARNING'], res.errors
"
```

### E. Expected Ingestion Command
```bash
python3 -c "
from scripts.ingest_reference_data import ingest_hydrological_csv
ingest_hydrological_csv(
    'data/reference/hydrology/bwdb_jamuna_river_stages_2024.csv',
    output_dir='data/processed/reference/hydrology',
    plausibility_range=(5.0, 20.0),
)
"
```

---

## 5. COPERNICUS GLO-30 DIGITAL SURFACE MODEL (DSM)

### A. Data Authority & Access Portal
- **Authority:** European Space Agency / Airbus Defence and Space / AWS Open Data Registry.
- **Access Portal:** AWS S3 Bucket `s3://copernicus-dem-30m/` or Copernicus Open Access Hub.
- **Product Type:** Copernicus DEM GLO-30 Public (1.0 arc-second, ~30 m).
- **Target Tile:** `Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif` (covering $24^\circ\text{N}$ to $25^\circ\text{N}$, $89^\circ\text{E}$ to $90^\circ\text{E}$).

### B. Required Files & Destination
Destination Directory:
`EarthPulse-SAR/data/reference/terrain/dem/`  
Target Filename: `Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif`

### C. Terrain Characterization & Limitations
- **Model Classification:** Digital Surface Model (DSM), NOT a bare-earth DEM.
- **Surface Contributions:** Elevations include vegetation canopy (3–15 m) and buildings.
- **Hydrological Constraints:** Cannot be used directly for hydrodynamic routing or HAND calculation without sink-filling, canopy removal, and stream carving.

### D. Acceptance Checks
```bash
python3 -c "
from scripts.validate_reference_inputs import validate_dem_dataset
res = validate_dem_dataset('data/reference/terrain/dem/Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif')
print('Status:', res.status)
assert res.status in ['READY', 'WARNING'], res.errors
"
```

### E. Expected Ingestion Command
```bash
python3 -c "
from scripts.ingest_reference_data import ingest_copernicus_dem
ingest_copernicus_dem(
    'data/reference/terrain/dem/Copernicus_DSM_COG_10_N24_00_E089_00_DEM.tif',
    output_dir='data/processed/reference/terrain',
)
"
```

---

## 6. VALIDATION AND AUDIT WORKFLOW

Once external reference files have been manually deposited into the reference directories:
1. Run the local reference inventory audit:
   ```bash
   python3 scripts/ingest_reference_data.py --scan-status
   ```
2. Verify that `data/metadata/phase4b_ingestion_status.json` updates from `BLOCKED` to `READY`.
3. Execute Phase 4A validation engine against primary candidate inundation masks:
   ```bash
   python3 scripts/validate_reference_data.py --evaluate-primary
   ```
4. Verify confusion matrix, Precision, Recall, F1, and IoU statistics.

