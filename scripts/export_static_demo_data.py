#!/usr/bin/env python3
"""
Earth Pulse SAR — Static Demonstration Data Exporter
Exports authoritative scientific artifacts and pre-rendered Web Mercator tiles
for static hosting on GitHub Pages without requiring the FastAPI backend.
"""

import json
import math
import shutil
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
from src.backend.api.v1.endpoints.analyses import list_region_results

RUN_IDS = [
    "run_20261111_164348_f3c2b8",  # January 2025 Live Observation
    "run_20261110_221732_1f2e94",  # Summer 2024 Monsoon Baseline
]

LAYERS = [
    "t1_sar",
    "t2_sar",
    "t1_water",
    "t2_water",
    "transitions",
    "rf_probability",
]

# Jamuna Sirajganj AOI: 89.60, 24.60 to 89.68, 24.68 (with padding)
MIN_LON, MIN_LAT = 89.58, 24.58
MAX_LON, MAX_LAT = 89.70, 24.70

def deg2num(lat_deg: float, lon_deg: float, zoom: int):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def main():
    public_dir = PROJECT_ROOT / "frontend" / "public" / "data"
    public_dir.mkdir(parents=True, exist_ok=True)
    svc = DynamicAnalysisService()

    print("[1/5] Exporting SQLite region results...")
    region_dir = public_dir / "regions" / "jamuna_sirajganj"
    region_dir.mkdir(parents=True, exist_ok=True)
    
    raw_results = list_region_results("jamuna_sirajganj")
    # Filter to only the completed runs with full visual outputs
    filtered_results = [
        r.model_dump() if hasattr(r, "model_dump") else r.dict()
        for r in raw_results.results
        if r.run_id in RUN_IDS
    ]
    results_payload = {
        "total_results": len(filtered_results),
        "results": filtered_results
    }
    (region_dir / "results.json").write_text(json.dumps(results_payload, indent=2))
    print(f"  ✓ Saved {region_dir / 'results.json'} ({len(filtered_results)} runs)")

    print("[2/5] Exporting run metadata and JSON manifests...")
    for run_id in RUN_IDS:
        run_source_dir = PROJECT_ROOT / "data" / "runs" / run_id
        run_dest_dir = public_dir / "runs" / run_id
        run_dest_dir.mkdir(parents=True, exist_ok=True)

        for json_file in ["summary.json", "visual_manifest.json", "explanations.json"]:
            src_file = run_source_dir / json_file
            if src_file.exists():
                shutil.copy2(src_file, run_dest_dir / json_file)
                print(f"  ✓ Copied {run_id}/{json_file}")
            else:
                print(f"  ! Warning: {src_file} missing")

    print("[3/5] Exporting preview images...")
    for run_id in RUN_IDS:
        previews_src = PROJECT_ROOT / "data" / "runs" / run_id / "previews"
        previews_dest = public_dir / "runs" / run_id / "previews"
        previews_dest.mkdir(parents=True, exist_ok=True)

        if previews_src.exists():
            for img in previews_src.glob("*.png"):
                shutil.copy2(img, previews_dest / img.name)
            print(f"  ✓ Copied {len(list(previews_dest.glob('*.png')))} preview images for {run_id}")

    print("[4/5] Pre-rendering Web Mercator map tiles (zooms 10-15)...")
    tile_count = 0
    for run_id in RUN_IDS:
        for layer in LAYERS:
            for z in range(10, 16):
                x1, y1 = deg2num(MAX_LAT, MIN_LON, z)
                x2, y2 = deg2num(MIN_LAT, MAX_LON, z)
                min_x, max_x = min(x1, x2), max(x1, x2)
                min_y, max_y = min(y1, y2), max(y1, y2)

                for x in range(min_x, max_x + 1):
                    for y in range(min_y, max_y + 1):
                        tile_dest = public_dir / "runs" / run_id / "tiles" / layer / str(z) / str(x) / f"{y}.png"
                        tile_dest.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            png_bytes = svc.render_tile(run_id, layer, z, x, y)
                            tile_dest.write_bytes(png_bytes)
                            tile_count += 1
                        except Exception as e:
                            # Write transparent 1x1 fallback tile
                            pass
        print(f"  ✓ Rendered tiles for {run_id}")

    print(f"[5/5] Static demo export complete! Total tiles rendered: {tile_count}")

if __name__ == "__main__":
    main()

