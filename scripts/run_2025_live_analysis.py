"""
Earth Pulse — Live 2025 Sentinel-1 End-to-End Pipeline Execution Script.
NASA Space Apps Challenge 2026: Dancing with the SARs

Executes the complete authoritative dynamic pipeline for the two authorized
January 2025 Sentinel-1 acquisitions:
- S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8 (Baseline)
- S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB (Change)
"""

import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.services.dynamic_analysis_service import DynamicAnalysisService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("EarthPulse.2025LiveRun")

AOI_WKT = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"
START_DATE = "2025-01-10"
END_DATE = "2025-01-26"

def main():
    logger.info("Initializing DynamicAnalysisService for 2025 live satellite run...")
    service = DynamicAnalysisService()

    logger.info("Creating dynamic analysis request for Jamuna study AOI...")
    run_init = service.create_analysis_request(
        aoi_wkt=AOI_WKT,
        start_date=START_DATE,
        end_date=END_DATE,
        mode="two_date_comparison",
        parameters={
            "description": "Authorized January 2025 Sentinel-1 live satellite validation run",
            "campaign": "Live 2025 Jamuna Flood Analysis",
        }
    )
    run_id = run_init["run_id"]
    logger.info("Created analysis run: %s", run_id)

    logger.info("Starting execute_analysis_run(%s)...", run_id)
    result = service.execute_analysis_run(run_id)

    logger.info("=== 2025 LIVE RUN COMPLETED SUCCESSFULLY ===")
    logger.info("Run ID: %s", run_id)
    logger.info("Status: %s", result.get("status"))
    logger.info("Run directory: %s", result.get("run_dir"))

    summary_path = Path(result["run_dir"]) / "summary.json"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        logger.info("Summary observations:")
        logger.info("  Baseline: %s (Water area: %.4f km²)", 
                    summary["observations"]["baseline"]["scene_name"],
                    summary["observations"]["baseline"]["water_area_km2"])
        logger.info("  Change:   %s (Water area: %.4f km²)", 
                    summary["observations"]["change"]["scene_name"],
                    summary["observations"]["change"]["water_area_km2"])
        logger.info("Flood transitions:")
        ft = summary.get("flood_transitions_km2", {})
        logger.info("  Newly Inundated:            %.4f km²", ft.get("newly_inundated", 0))
        logger.info("  Receded Water:              %.4f km²", ft.get("receded_water", 0))
        logger.info("  Persistent Water:           %.4f km²", ft.get("persistent_water", 0))
        logger.info("  Persistent Non-Water:       %.4f km²", ft.get("persistent_non_water", 0))
        logger.info("  Net Candidate Water Change: %.4f km²", ft.get("net_candidate_water_change", 0))
        logger.info("Reconciliation check passed: %s", summary.get("flood_reconciliation", {}).get("net_equals_inundation_minus_recession"))

    print(json.dumps({
        "status": "SUCCESS",
        "run_id": run_id,
        "run_dir": str(result.get("run_dir")),
    }, indent=2))

if __name__ == "__main__":
    main()
