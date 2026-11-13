# Earth Pulse SAR Backend — Frontend API Contract Specification
**NASA Space Apps Challenge 2026: Dancing with the SARs**  
**Version:** 1.0.0 (Production Release Candidate)  
**Base URL:** `http://localhost:8000/api/v1`

---

## 1. Overview & Connection Architecture

The Earth Pulse backend provides RESTful endpoints for Sentinel-1 radar observation discovery, on-demand ESA SNAP dual-polarization preprocessing, calibrated Otsu flood classification, common-domain flood change accounting, morphological riverbank migration analysis, Random Forest water probability mapping, and Saabas local explainable AI (XAI).

All endpoints deliver production-validated JSON schemas and web-ready mapping assets (XYZ tile templates, PNG preview images, and georeferenced GeoTIFFs).

### Authentication & Public Safety Modes
- **Demo Mode Execution (`DEMO_MODE_RESTRICTED_EXECUTION=true`)**: Protects host compute by allowing execution only on pre-authorized study windows (`2024-06-10` to `2024-07-16` historical baseline, and `2025-01-12` to `2025-01-24` genuine SAR live verification). Unauthenticated requests for non-demo date ranges receive `HTTP 403 Forbidden`.
- **Private Production Mode (`DEMO_MODE_RESTRICTED_EXECUTION=false`)**: Full dynamic ASF search, Earthdata download, and ESA SNAP preprocessing for arbitrary user-defined AOIs within the Jamuna river basin.

### CORS Configuration
Cross-Origin Resource Sharing is configured via the `ALLOWED_ORIGINS` environment variable (comma-separated). Default origins include:
- `http://localhost:3000`, `http://127.0.0.1:3000` (Next.js / React)
- `http://localhost:5173`, `http://127.0.0.1:5173` (Vite)
- `http://localhost:8000`, `http://127.0.0.1:8000` (Local Swagger UI / Docs)

---

## 2. API Endpoints Catalog

### 2.1 Dynamic Observation Discovery
#### `POST /api/v1/catalog/sentinel1/search`
Searches NASA Alaska Satellite Facility (ASF) DAAC for Sentinel-1 IW GRD acquisitions covering the submitted AOI and date range, identifying dual-polarization (VV+VH) products and determining compatible temporal pairs (same relative orbit and flight direction).

**Request Body (`application/json`):**
```json
{
  "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
  "start_date": "2024-06-10",
  "end_date": "2024-07-16",
  "orbit_direction": null,
  "relative_orbit": null,
  "max_results": 50
}
```

**Response (`200 OK`):**
```json
{
  "total_scenes": 2,
  "scenes": [
    {
      "scene_id": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
      "acquisition_date": "2024-06-10",
      "acquisition_time": "2024-06-10T12:05:08Z",
      "flight_direction": "DESCENDING",
      "orbit_number": 54261,
      "relative_orbit": 40,
      "polarizations": ["VV", "VH"],
      "download_url": "https://datapool.asf.alaska.edu/GRD_HD/SA/...",
      "size_mb": 984.5
    },
    {
      "scene_id": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
      "acquisition_date": "2024-07-16",
      "acquisition_time": "2024-07-16T12:05:07Z",
      "flight_direction": "DESCENDING",
      "orbit_number": 54786,
      "relative_orbit": 40,
      "polarizations": ["VV", "VH"],
      "download_url": "https://datapool.asf.alaska.edu/GRD_HD/SA/...",
      "size_mb": 988.2
    }
  ],
  "compatible_pairs_count": 1,
  "compatible_pairs": [
    {
      "baseline": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
      "change": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
      "days_interval": 36,
      "relative_orbit": 40,
      "direction": "DESCENDING"
    }
  ]
}
```
*Note: Returns exact serialized response keys (`total_scenes`, `scenes`, `compatible_pairs_count`, `compatible_pairs`). Does not emit invented top-level `status` or `aoi_wkt`.*

---

### 2.2 Analysis Job Submission & Status
#### `POST /api/v1/analysis-requests`
Submits a dynamic satellite analysis run for background or synchronous execution.

**Request Body (`application/json`):**
```json
{
  "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
  "start_date": "2024-06-10",
  "end_date": "2024-07-16",
  "mode": "two_date_comparison",
  "parameters": {},
  "run_synchronously": false
}
```

**Response (`200 OK`):**
```json
{
  "run_id": "run_20261112_010000_a1b2c3",
  "status": "CREATED",
  "progress_pct": 0.0,
  "request": {
    "run_id": "run_20261112_010000_a1b2c3",
    "mode": "two_date_comparison",
    "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
    "start_date": "2024-06-10",
    "end_date": "2024-07-16",
    "satellite_acquisitions": ["2024-06-10", "2024-07-16"],
    "parameters": {},
    "created_at": "2026-11-12T01:00:00.000000+00:00"
  }
}
```
*Status Code Note: The endpoint returns `200 OK` (FastAPI standard default), NOT `202 Accepted`.*

#### `GET /api/v1/analysis-requests/{run_id}`
Retrieves real-time status and progress percentage of a submitted job.

**Response (`200 OK`):**
```json
{
  "run_id": "run_20261111_164348_f3c2b8",
  "status": "COMPLETED",
  "stage": "COMPLETED",
  "progress_pct": 100.0,
  "message": "Dynamic analysis pipeline completed successfully.",
  "error": null,
  "created_at": "2026-11-11T16:43:48.000000+00:00",
  "updated_at": "2026-11-11T16:47:12.000000+00:00"
}
```

#### `POST /api/v1/analysis-requests/{run_id}/cancel`
Requests cooperative cancellation of an active pipeline job.

---

### 2.3 Scientific Summary & Reconciliation
#### `GET /api/v1/runs/{run_id}/summary`
Retrieves the complete scientific accounting report, invariant flood changes, riverbank transect measurements, and machine learning evaluations.

**Response (`200 OK`):**
```json
{
  "run_id": "run_20261111_164348_f3c2b8",
  "status": "COMPLETED",
  "completed_at": "2026-11-11T16:47:12.128795+00:00",
  "study_aoi": {
    "name": "Jamuna River Reach - Sirajganj",
    "wkt": "POLYGON ((89.65 24.58, 89.75 24.58, 89.75 24.76, 89.65 24.76, 89.65 24.58))",
    "area_km2": 200.0
  },
  "observations": {
    "baseline": {
      "acquisition_date": "2025-01-12",
      "acquisition_time": "2025-01-12T12:05:03Z",
      "granule": "S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
      "water_area_km2": 11.9852,
      "otsu_threshold_db": -16.82
    },
    "change": {
      "acquisition_date": "2025-01-24",
      "acquisition_time": "2025-01-24T12:05:02Z",
      "granule": "S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB",
      "water_area_km2": 13.0292,
      "otsu_threshold_db": -16.94
    }
  },
  "flood_transitions_km2": {
    "persistent_water": 11.4132,
    "newly_inundated": 1.6160,
    "receded_water": 0.5720,
    "persistent_non_water": 56.0104,
    "indeterminate_noise_floor": 0.0,
    "net_candidate_water_change": 1.0440
  },
  "flood_reconciliation": {
    "net_equals_inundation_minus_recession": true,
    "calculated_net_change_km2": 1.0440,
    "reconciliation_discrepancy_km2": 0.0,
    "accounting_precision": "1e-4 km2"
  },
  "riverbank_dynamics": {
    "total_transects_evaluated": 36,
    "valid_migration_transects": 35,
    "unqualified_transects": 1,
    "unqualified_row_indices": [396],
    "channel_correspondence_status": "QUALIFIED_CORRESPONDENCE_ESTABLISHED",
    "mean_left_bank_displacement_m": 45.71,
    "mean_right_bank_displacement_m": 1.71,
    "mean_net_migration_m": 22.0,
    "maximum_bank_displacement_m": 360.0
  },
  "ai_evaluation": {
    "model_id": "phase7a_rf_jamuna_v1",
    "overall_accuracy": 0.9412,
    "water_f1_score": 0.9284,
    "xai_engine": "saabas_tree_path_decomposition",
    "additivity_verified": true
  }
}
```

---

### 2.4 Interactive Map Layers & Visual Manifest
#### `GET /api/v1/runs/{run_id}/visual-manifest`
Provides the full map-layer catalog, geographic bounds, XYZ tile templates, preview URLs, and color legends formatted for Leaflet, Mapbox GL JS, or OpenLayers.

**Response (`200 OK`):**
```json
{
  "run_id": "run_20261111_164348_f3c2b8",
  "status": "COMPLETED",
  "completed_at": "2026-11-11T16:47:12.128795+00:00",
  "geographic_bounds": {
    "epsg4326": [89.65, 24.58, 89.75, 24.76],
    "epsg32645": [363240.0, 2719200.0, 373380.0, 2739220.0],
    "center": {"lon": 89.70, "lat": 24.67}
  },
  "pixel_spacing_m": [20.0, 20.0],
  "layers": [
    {
      "layer_id": "t1_sar",
      "title": "Baseline Sentinel-1 Radar Backscatter (VV)",
      "type": "raster_continuous",
      "observation_date": "2025-01-12T12:05:03Z",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/t1_sar/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/t1_sar.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/t1_calibrated.tif",
      "legend": {"type": "continuous", "min_db": -25.0, "max_db": 0.0, "units": "dB"}
    },
    {
      "layer_id": "t2_sar",
      "title": "Observation Sentinel-1 Radar Backscatter (VV)",
      "type": "raster_continuous",
      "observation_date": "2025-01-24T12:05:02Z",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/t2_sar/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/t2_sar.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/t2_calibrated.tif",
      "legend": {"type": "continuous", "min_db": -25.0, "max_db": 0.0, "units": "dB"}
    },
    {
      "layer_id": "t1_water",
      "title": "Baseline Candidate Water Classification",
      "type": "raster_categorical",
      "observation_date": "2025-01-12T12:05:03Z",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/t1_water/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/t1_water.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/t1_water_mask.tif",
      "legend": {
        "type": "categorical",
        "classes": [
          {"value": 1, "label": "Candidate Water", "color": "#08519c", "area_km2": 11.9852},
          {"value": 0, "label": "Non-Water Land", "color": "#d9d9d9"},
          {"value": 2, "label": "Indeterminate Noise Floor", "color": "#a6cee3"}
        ]
      }
    },
    {
      "layer_id": "t2_water",
      "title": "Observation Candidate Water Classification",
      "type": "raster_categorical",
      "observation_date": "2025-01-24T12:05:02Z",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/t2_water/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/t2_water.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/t2_water_mask.tif",
      "legend": {
        "type": "categorical",
        "classes": [
          {"value": 1, "label": "Candidate Water", "color": "#08519c", "area_km2": 13.0292},
          {"value": 0, "label": "Non-Water Land", "color": "#d9d9d9"},
          {"value": 2, "label": "Indeterminate Noise Floor", "color": "#a6cee3"}
        ]
      }
    },
    {
      "layer_id": "transitions",
      "title": "Flood Inundation & Transition Dynamics",
      "type": "raster_categorical",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/transitions/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/flood_transitions.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/transition_classes.tif",
      "legend": {
        "type": "categorical",
        "classes": [
          {"value": 1, "label": "Persistent Water", "color": "#08519c", "area_km2": 11.4132},
          {"value": 2, "label": "Newly Inundated (Expansion)", "color": "#41b6c4", "area_km2": 1.6160},
          {"value": 3, "label": "Receded Water (Recession)", "color": "#fe9929", "area_km2": 0.5720},
          {"value": 4, "label": "Persistent Non-Water Land", "color": "#cccccc", "area_km2": 56.0104},
          {"value": 5, "label": "Indeterminate Noise Floor", "color": "#a6cee3", "area_km2": 0.0},
          {"value": 6, "label": "Outside AOI / NoData", "color": "#00000000", "area_km2": 0.0}
        ]
      }
    },
    {
      "layer_id": "rf_probability",
      "title": "Random Forest Continuous Water Probability",
      "type": "raster_continuous",
      "tile_url_template": "/api/v1/runs/run_20261111_164348_f3c2b8/tiles/rf_probability/{z}/{x}/{y}.png",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/rf_probability.png",
      "download_geotiff_url": "/api/v1/runs/run_20261111_164348_f3c2b8/download/rf_probability.tif",
      "legend": {
        "type": "continuous",
        "min": 0.0,
        "max": 1.0,
        "decision_threshold": 0.35,
        "colormap": "cividis"
      }
    },
    {
      "layer_id": "riverbank_migration",
      "title": "Riverbank Migration & Channel Dynamics",
      "type": "vector_or_raster",
      "preview_png_url": "/api/v1/runs/run_20261111_164348_f3c2b8/previews/riverbank_migration.png",
      "metrics": {
        "valid_migration_transects": 35,
        "unqualified_transects": 1,
        "mean_left_displacement_m": 45.71,
        "mean_right_displacement_m": 1.71
      }
    }
  ]
}
```

---

### 2.5 Map Tile Serving & Static Previews
#### `GET /api/v1/runs/{run_id}/tiles/{layer_id}/{z}/{x}/{y}.png`
Delivers 256×256 PNG map tiles conforming to the Standard Web Mercator (EPSG:3857) Slippy Map specification with LRU in-memory caching.
- `layer_id` options: `t1_sar`, `t2_sar`, `t1_water`, `t2_water`, `transitions`, `rf_probability`.
- Outside-AOI / NoData pixels (Class 6) render as fully transparent (`#00000000`).

#### `GET /api/v1/runs/{run_id}/previews/{asset_name}`
Returns standalone publication-ready PNG images including title banner, geographic scale bar, north arrow, and colormap legend.
- Accepted values for `asset_name`: `flood_transitions.png`, `riverbank_migration.png`, `rf_probability.png`, `t1_sar.png`, `t2_sar.png`.

#### `GET /api/v1/runs/{run_id}/download/{filename}`
Streams full 32-bit floating-point or 8-bit categorical GeoTIFF rasters with geospatial metadata (EPSG:32645 UTM 45N projection) and Deflate/LZW compression.

---

### 2.6 Machine Learning & Explainable AI
#### `GET /api/v1/runs/{run_id}/explanations`
Returns sample pixel-level local feature attributions computed via Saabas exact decision-tree path decomposition.

**Response (`200 OK`):**
```json
{
  "run_id": "run_20261111_164348_f3c2b8",
  "model_id": "phase7a_rf_jamuna_v1",
  "mean_water_probability": 0.532,
  "additivity_verified": true,
  "feature_names": [
    "vv_db",
    "vh_db",
    "vh_vv_ratio_db",
    "ndwi_proxy",
    "vv_local_mean_3x3",
    "vh_local_mean_3x3",
    "ratio_local_std_3x3"
  ],
  "sample_explanations": [
    {
      "sample_index": 0,
      "base_value": 0.5280,
      "prediction_probability": 0.9412,
      "attributions": {
        "vv_db": 0.2150,
        "vh_db": 0.1042,
        "vh_vv_ratio_db": -0.0120,
        "ndwi_proxy": 0.0540,
        "vv_local_mean_3x3": 0.0380,
        "vh_local_mean_3x3": 0.0125,
        "ratio_local_std_3x3": 0.0015
      },
      "additivity_error": 0.0,
      "is_additive": true
    }
  ]
}
```
*Additivity Guarantee: For every sample, `prediction_probability == base_value + sum(attributions)` within numerical tolerance `< 1e-6`.*

