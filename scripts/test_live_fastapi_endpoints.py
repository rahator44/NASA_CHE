"""
Test FastAPI endpoints against the real 2025 Sentinel-1 run.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import sys
import json
from pathlib import Path
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.main import app

RUN_ID = "run_20261111_164348_f3c2b8"
AOI_WKT = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"

def main():
    client = TestClient(app)
    results = {}

    # 1. GET /health
    resp = client.get("/health")
    print(f"GET /health: {resp.status_code}")
    assert resp.status_code == 200
    results["health"] = resp.json()

    # 2. POST /api/v1/catalog/sentinel1/search
    search_payload = {
        "aoi_wkt": AOI_WKT,
        "start_date": "2025-01-10",
        "end_date": "2025-01-26",
    }
    resp = client.post("/api/v1/catalog/sentinel1/search", json=search_payload)
    print(f"POST /api/v1/catalog/sentinel1/search: {resp.status_code}")
    assert resp.status_code == 200
    search_data = resp.json()
    assert search_data.get("total_scenes", 0) >= 2
    results["catalog_search"] = {"total_scenes": search_data.get("total_scenes"), "status": resp.status_code}

    # 3. GET /api/v1/analysis-requests/{run_id}
    resp = client.get(f"/api/v1/analysis-requests/{RUN_ID}")
    print(f"GET /api/v1/analysis-requests/{RUN_ID}: {resp.status_code}")
    assert resp.status_code == 200
    req_status = resp.json()
    assert req_status.get("status") == "COMPLETED"
    results["analysis_request"] = req_status

    # 4. GET /api/v1/runs/{run_id}/summary
    resp = client.get(f"/api/v1/runs/{RUN_ID}/summary")
    print(f"GET /api/v1/runs/{RUN_ID}/summary: {resp.status_code}")
    assert resp.status_code == 200
    summary_data = resp.json()
    assert summary_data["status"] == "COMPLETED"
    assert summary_data["observations"]["baseline"]["scene_name"].startswith("S1A_IW_GRDH_1SDV_20250112")
    assert summary_data["observations"]["change"]["scene_name"].startswith("S1A_IW_GRDH_1SDV_20250124")
    assert summary_data["flood_reconciliation"]["net_equals_inundation_minus_recession"] is True
    results["summary"] = {
        "status": summary_data["status"],
        "net_candidate_water_change": summary_data["flood_transitions_km2"]["net_candidate_water_change"],
        "t1_scene": summary_data["observations"]["baseline"]["scene_name"],
        "t2_scene": summary_data["observations"]["change"]["scene_name"],
    }

    # 5. GET /api/v1/runs/{run_id}/visual-manifest
    resp = client.get(f"/api/v1/runs/{RUN_ID}/visual-manifest")
    print(f"GET /api/v1/runs/{RUN_ID}/visual-manifest: {resp.status_code}")
    assert resp.status_code == 200
    manifest_data = resp.json()
    assert manifest_data["status"] == "COMPLETED"
    assert len(manifest_data.get("layers", [])) > 0
    results["visual_manifest"] = {
        "status": manifest_data["status"],
        "layers_count": len(manifest_data.get("layers", [])),
    }

    # 6. GET /api/v1/runs/{run_id}/rasters
    resp = client.get(f"/api/v1/runs/{RUN_ID}/rasters")
    print(f"GET /api/v1/runs/{RUN_ID}/rasters: {resp.status_code}")
    assert resp.status_code == 200
    rasters_data = resp.json()
    assert len(rasters_data) > 0
    results["rasters"] = {"count": len(rasters_data)}

    # 7. GET /api/v1/runs/{run_id}/explanations
    resp = client.get(f"/api/v1/runs/{RUN_ID}/explanations")
    print(f"GET /api/v1/runs/{RUN_ID}/explanations: {resp.status_code}")
    assert resp.status_code == 200
    exp_data = resp.json()
    assert exp_data.get("additivity_verified") is True
    results["explanations"] = {
        "additivity_verified": exp_data.get("additivity_verified"),
        "mean_water_probability": exp_data.get("mean_water_probability"),
    }

    # 8. GET preview PNG route
    resp = client.get(f"/api/v1/runs/{RUN_ID}/previews/preview_flood_transitions.png")
    print(f"GET preview PNG: {resp.status_code}, content-type={resp.headers.get('content-type')}")
    assert resp.status_code == 200
    assert "image/png" in resp.headers.get("content-type", "")
    assert len(resp.content) > 10000

    # 9. GET download raster route
    resp = client.get(f"/api/v1/runs/{RUN_ID}/download/transition_classes.tif")
    print(f"GET download raster: {resp.status_code}, length={len(resp.content)}")
    assert resp.status_code == 200
    assert len(resp.content) > 1000

    # 10. GET XYZ tile route
    # Bounds center is around lat 24.64, lon 89.64. At z=12, calculate x, y
    import math
    lat_rad = math.radians(24.64005)
    n = 2.0 ** 12
    tile_x = int((89.63997 + 180.0) / 360.0 * n)
    tile_y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    resp = client.get(f"/api/v1/runs/{RUN_ID}/tiles/flood_transitions/{12}/{tile_x}/{tile_y}.png")
    print(f"GET XYZ tile (z=12, x={tile_x}, y={tile_y}): {resp.status_code}, content-type={resp.headers.get('content-type')}")
    assert resp.status_code == 200
    assert "image/png" in resp.headers.get("content-type", "")

    print("\nALL FASTAPI ENDPOINTS VERIFIED!")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
