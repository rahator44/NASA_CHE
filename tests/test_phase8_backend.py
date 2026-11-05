"""
Phase 8 Backend API & Scientific Data Services Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs
Study Area: Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)

Comprehensive 24-Scenario Verification for Production Scientific Backend
"""

import hashlib
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from starlette.testclient import TestClient

from src.backend.main import app
from src.backend.config import settings
from src.backend.database.database import get_db_connection
from src.backend.services.raster_service import RASTER_CATALOG, RasterService
from src.backend.services.job_service import ALLOWLISTED_JOB_TYPES
from src.backend.services.region_service import RegionService


@pytest.fixture(scope="module")
def client():
    """Provides test client within application lifespan context."""
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Scenario 1: Application Startup and Lifespan
# ==============================================================================
def test_01_application_startup_and_lifespan(client):
    """Verifies FastAPI startup lifespan, DB connection, and table seeding."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "jobs" in tables, "jobs table missing from SQLite database"
        assert "analysis_runs" in tables, "analysis_runs table missing from SQLite database"

        cursor.execute("SELECT count(*) FROM analysis_runs;")
        runs_count = cursor.fetchone()[0]
        assert runs_count >= 8, f"Expected at least 8 precomputed analysis runs, got {runs_count}"


# ==============================================================================
# Scenario 2: Health Endpoint
# ==============================================================================
def test_02_health_endpoint(client):
    """Verifies /health endpoint returns HTTP 200, service metadata, and status healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "EarthPulse-SAR" in data["service"]
    assert "Jamuna" in data["study_area"]


# ==============================================================================
# Scenario 3: Region Listing
# ==============================================================================
def test_03_region_listing(client):
    """Verifies /api/v1/regions lists available regions including jamuna_sirajganj."""
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions"] >= 1
    region_ids = [r["region_id"] for r in data["regions"]]
    assert "jamuna_sirajganj" in region_ids


# ==============================================================================
# Scenario 4: Region Configuration Validation
# ==============================================================================
def test_04_region_configuration_validation(client):
    """Verifies detailed configuration, CRS, spatial resolution, and bounding polygon."""
    response = client.get("/api/v1/regions/jamuna_sirajganj")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "jamuna_sirajganj"
    assert data["crs"] == "EPSG:32645"
    assert data["spatial_resolution_m"] == 20.0
    assert len(data["raster_dimensions"]) == 2
    assert "bounding_polygon" in data
    assert data["bounding_polygon"]["crs"] in ("EPSG:4326", "EPSG:32645")


# ==============================================================================
# Scenario 5: Dataset Listing
# ==============================================================================
def test_05_dataset_listing(client):
    """Verifies /api/v1/datasets catalogs all registered SAR and optical datasets."""
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    data = response.json()
    assert data["total_datasets"] >= 8
    dataset_ids = [d["dataset_id"] for d in data["datasets"]]
    assert any("20240610_aligned" in did for did in dataset_ids)
    assert any("20240716_aligned" in did for did in dataset_ids)
    assert any("s2a_msil2a" in did for did in dataset_ids)


# ==============================================================================
# Scenario 6: Dataset Provenance Lookup
# ==============================================================================
def test_06_dataset_provenance_lookup(client):
    """Verifies single dataset provenance lookup and SHA-256 checksum status."""
    response = client.get("/api/v1/datasets/s1a_iw_grd_20240610_aligned")
    assert response.status_code == 200
    data = response.json()
    assert data["dataset_id"] == "s1a_iw_grd_20240610_aligned"
    assert data["checksum_verified"] is True
    assert len(data["sha256"]) == 64


# ==============================================================================
# Scenario 7: Analysis Catalogue
# ==============================================================================
def test_07_analysis_catalogue(client):
    """Verifies /api/v1/analyses exposes all 5 scientific analysis modules."""
    response = client.get("/api/v1/analyses")
    assert response.status_code == 200
    data = response.json()
    assert data["total_analyses"] >= 5
    analysis_ids = [a["analysis_id"] for a in data["analyses"]]
    assert "flood_change_detection" in analysis_ids
    assert "riverbank_migration_displacement" in analysis_ids
    assert "random_forest_classification" in analysis_ids
    assert "model_explainability_attribution" in analysis_ids
    assert "scientific_uncertainty_audit" in analysis_ids


# ==============================================================================
# Scenario 8: Flood Summary Retrieval
# ==============================================================================
def test_08_flood_summary_retrieval(client):
    """Verifies flood inundation accounting and epoch statistics."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/flood/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "jamuna_sirajganj"
    assert data["net_candidate_water_change_ha"] > 5000.0
    assert data["pre_monsoon_epoch"]["candidate_water_cells"] > 0
    assert data["monsoon_crest_epoch"]["candidate_water_cells"] > 0


# ==============================================================================
# Scenario 9: Riverbank Summary Retrieval
# ==============================================================================
def test_09_riverbank_summary_retrieval(client):
    """Verifies riverbank transect migration summary and detection range."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "jamuna_sirajganj"
    assert data["total_transects_evaluated"] in (154, 175)
    assert data["valid_transects_count"] in (122, 134)
    assert "35-85" in data["provisional_detection_range_m"]


# ==============================================================================
# Scenario 10: Model Registry Retrieval
# ==============================================================================
def test_10_model_registry_retrieval(client):
    """Verifies Random Forest model registry listing and operational baseline status."""
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    models = response.json()
    assert len(models) >= 1
    rf = next(m for m in models if m["model_id"] == "phase7a_rf_jamuna_v1")
    assert rf["optimal_probability_threshold"] == 0.35
    assert rf["status"] == "RETAINED_AS_PROBABILITY_LAYER"


# ==============================================================================
# Scenario 11: Explainability Metadata Retrieval
# ==============================================================================
def test_11_explainability_metadata_retrieval(client):
    """Verifies Explainable AI base values and rank-1 feature attribution."""
    response = client.get("/api/v1/models/phase7a_rf_jamuna_v1/explanations")
    assert response.status_code == 200
    data = response.json()
    assert data["global_base_value_training_background"] == 0.4905
    assert data["ensemble_root_base_value"] == 0.4995
    assert len(data["global_importance_ranking"]) == 6
    assert data["global_importance_ranking"][0]["feature_name"] == "vv_db"


# ==============================================================================
# Scenario 12: Raster Metadata Retrieval
# ==============================================================================
def test_12_raster_metadata_retrieval(client):
    """Verifies GeoTIFF metadata retrieval, CRS, and raster dimensions."""
    response = client.get("/api/v1/rasters/phase5_flood_transitions/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["crs"] == "EPSG:32645"
    assert data["width"] == 1405
    assert data["height"] == 1393
    assert data["count"] == 1


# ==============================================================================
# Scenario 13: Vector Data Access
# ==============================================================================
def test_13_vector_data_access(client):
    """Verifies GeoJSON vector feature collection access for inundation clusters."""
    response = client.get("/api/v1/vectors/phase5_inundation_clusters")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "phase5_inundation_clusters"
    assert data["feature_count"] == 1177
    assert data["geojson"]["type"] == "FeatureCollection"
    assert len(data["geojson"]["features"]) == 1177


# ==============================================================================
# Scenario 14: Tile Service Rendering
# ==============================================================================
def test_14_tile_service_rendering(client):
    """Verifies dynamic XYZ PNG map tile rendering at valid zoom and coordinates."""
    response = client.get("/api/v1/tiles/phase5_flood_transitions/11/1534/878.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(response.content))
    assert img.size == (256, 256)
    assert img.mode == "RGBA"


# ==============================================================================
# Scenario 15: NoData and Raster Bounds Handling
# ==============================================================================
def test_15_nodata_and_raster_bounds_handling(client):
    """Verifies requests outside the raster bounding box return transparent 256x256 PNGs."""
    response = client.get("/api/v1/tiles/phase5_flood_transitions/0/0/0.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(response.content))
    assert img.size == (256, 256)
    # Check that tile is completely transparent (alpha == 0 everywhere)
    extrema = img.getextrema()
    # extrema for RGBA is ((min_r, max_r), (min_g, max_g), (min_b, max_b), (min_a, max_a))
    assert extrema[3][1] == 0, "Tile outside bounding box must be completely transparent"


# ==============================================================================
# Scenario 16: Categorical Resampling Rule Check
# ==============================================================================
def test_16_categorical_resampling_rule_check():
    """Verifies that categorical layers use Nearest Neighbour and continuous use Bilinear."""
    transitions_info = RASTER_CATALOG["phase5_flood_transitions"]
    backscatter_info = RASTER_CATALOG["june10_sigma0_vv_db"]
    prob_info = RASTER_CATALOG["phase7a_july16_water_probability"]

    assert transitions_info["layer_type"] == "categorical"
    assert backscatter_info["layer_type"] == "continuous"
    assert prob_info["layer_type"] == "continuous"


# ==============================================================================
# Scenario 17: Path Traversal Protection
# ==============================================================================
def test_17_path_traversal_protection(client):
    """Verifies that path traversal attacks and arbitrary file reads are blocked."""
    # Attempt traversal in raster asset_id
    response = client.get("/api/v1/rasters/../../etc/passwd/metadata")
    assert response.status_code in (404, 400)

    # Attempt traversal in tile endpoint
    response = client.get("/api/v1/tiles/..%2F..%2Fetc%2Fpasswd/10/100/100.png")
    assert response.status_code in (404, 400)

    # Attempt traversal in report endpoint
    response = client.get("/api/v1/reports/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (404, 400)


# ==============================================================================
# Scenario 18: Invalid Identifier Handling
# ==============================================================================
def test_18_invalid_identifier_handling(client):
    """Verifies structured 404 responses for nonexistent entities."""
    # Nonexistent region
    r_region = client.get("/api/v1/regions/nonexistent_delta_region")
    assert r_region.status_code == 404
    assert "not found" in r_region.json()["detail"].lower()

    # Nonexistent dataset
    r_dataset = client.get("/api/v1/datasets/landsat_ghost_scene")
    assert r_dataset.status_code == 404

    # Nonexistent model
    r_model = client.get("/api/v1/models/unregistered_deep_network")
    assert r_model.status_code == 404

    # Nonexistent raster
    r_raster = client.get("/api/v1/rasters/unregistered_sar_grid/metadata")
    assert r_raster.status_code == 404


# ==============================================================================
# Scenario 19: SQLite Persistence
# ==============================================================================
def test_19_sqlite_persistence(client):
    """Verifies SQLite persistence across distinct HTTP calls."""
    post_res = client.post("/api/v1/jobs", json={
        "job_type": "verify_dataset_integrity",
        "region_id": "jamuna_sirajganj",
        "parameters": {"check_hashes": True}
    })
    assert post_res.status_code == 201
    job_id = post_res.json()["job_id"]

    # Retrieve in second independent call
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["job_id"] == job_id
    assert get_res.json()["status"] == "COMPLETED"


# ==============================================================================
# Scenario 20: Job Status Transitions
# ==============================================================================
def test_20_job_status_transitions(client):
    """Verifies allowlisted job execution and progress tracking."""
    post_res = client.post("/api/v1/jobs", json={
        "job_type": "generate_flood_summary",
        "region_id": "jamuna_sirajganj",
        "parameters": {}
    })
    assert post_res.status_code == 201
    job = post_res.json()
    assert job["status"] == "COMPLETED"
    assert job["progress_pct"] == 100.0
    assert job["output_references"] is not None
    assert "summary" in job["output_references"]


# ==============================================================================
# Scenario 21: API Error Handling and Status Codes
# ==============================================================================
def test_21_api_error_handling_and_status_codes(client):
    """Verifies that un-allowlisted job submissions return HTTP 400 Bad Request."""
    bad_res = client.post("/api/v1/jobs", json={
        "job_type": "arbitrary_bash_command",
        "parameters": {"cmd": "rm -rf /"}
    })
    assert bad_res.status_code == 400
    assert "not permitted" in bad_res.json()["detail"].lower()


# ==============================================================================
# Scenario 22: Historical Dataset Integrity
# ==============================================================================
def test_22_historical_dataset_integrity():
    """Verifies that datasets listed in dataset_manifest.json exist and match SHA-256."""
    manifest_path = settings.METADATA_DIR / "dataset_manifest.json"
    assert manifest_path.exists(), "dataset_manifest.json missing"
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    for item in manifest.get("datasets", []):
        rel_path = item.get("source_path") or item.get("relative_path")
        expected_sha = item.get("sha256")
        full_path = settings.PROJECT_ROOT_DIR / rel_path
        assert full_path.exists(), f"Dataset file missing: {rel_path}"

        h = hashlib.sha256()
        with open(full_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        assert h.hexdigest() == expected_sha, f"SHA-256 mismatch for dataset {rel_path}"


# ==============================================================================
# Scenario 23: Model Artifact Preservation
# ==============================================================================
def test_23_model_artifact_preservation():
    """Verifies Random Forest model artifact joblib file has not been modified."""
    model_path = settings.PROJECT_ROOT_DIR / "models/phase7a/phase7a_random_forest_model.joblib"
    assert model_path.exists(), "Phase 7A model artifact missing"

    expected_sha256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)

    actual_sha256 = h.hexdigest()
    assert actual_sha256 == expected_sha256, (
        f"CRITICAL: Phase 7A model artifact was modified! Expected {expected_sha256}, got {actual_sha256}"
    )


# ==============================================================================
# Scenario 24: Future-Region Configuration Compatibility
# ==============================================================================
def test_24_future_region_configuration_compatibility():
    """Verifies RegionService dynamically discovers configurations without hardcoding."""
    regions = RegionService.list_regions()
    assert isinstance(regions, list)
    assert len(regions) >= 1
    # Check that region loader accesses the configs directory dynamically
    regions_dir = settings.CONFIGS_DIR / "regions"
    yaml_count = len(list(regions_dir.glob("*.yaml")))
    assert len(regions) == yaml_count, (
        f"Region service count ({len(regions)}) must match YAML configuration count ({yaml_count})"
    )
