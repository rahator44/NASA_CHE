"""
Scientific Reports & Aggregated Statistics Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.backend.config import settings

REPORT_CATALOG: Dict[str, Dict[str, str]] = {
    "phase1_alignment": {
        "phase": "Phase 1",
        "title": "SAR Dual-Date Co-Registration and Grid Alignment Report",
        "category": "Pre-Processing & Spatial Co-Registration",
        "filename": "phase1_alignment_report.json",
    },
    "phase2a_backscatter": {
        "phase": "Phase 2A",
        "title": "Calibrated Sigma0 Backscatter and Temporal Differencing Report",
        "category": "Radiometric Calibration",
        "filename": "phase2a_analysis_report.json",
    },
    "phase2b_filtering": {
        "phase": "Phase 2B",
        "title": "Adaptive Spatial Speckle Filtering & ENL Optimization Report",
        "category": "Speckle Suppression",
        "filename": "phase2b_filtering_report.json",
    },
    "phase3a_classification": {
        "phase": "Phase 3A",
        "title": "Adaptive Otsu & Kittler-Illingworth Water Classification Report",
        "category": "Deterministic Thresholding",
        "filename": "phase3a_classification_report.json",
    },
    "phase3b_change_detection": {
        "phase": "Phase 3B",
        "title": "Two-Epoch Flood Inundation & Change Detection Report",
        "category": "Change Detection",
        "filename": "phase3b_change_detection_report.json",
    },
    "phase4c1_optical_ingestion": {
        "phase": "Phase 4C.1",
        "title": "Sentinel-2 Optical Reference Data Ingestion & Quality Control",
        "category": "Reference Data Ingestion",
        "filename": "phase4c1_sentinel2_ingestion_report.json",
    },
    "phase4d1_validation_reconciliation": {
        "phase": "Phase 4D.1",
        "title": "Independent Optical-Reference Validation Reconciliation Report",
        "category": "Validation & Quality Control",
        "filename": "phase4d1_reconciliation_report.json",
    },
    "phase5_flood_change": {
        "phase": "Phase 5",
        "title": "Final SAR Flood-Change Engine & Inundation Area Accounting",
        "category": "Operational Inundation Accounting",
        "filename": "phase5_flood_change_report.json",
    },
    "phase6_riverbank_migration": {
        "phase": "Phase 6",
        "title": "Riverbank Migration, Channel-Margin Displacement & Erosion Analysis",
        "category": "Fluvial Geomorphology",
        "filename": "phase6_riverbank_migration_report.json",
    },
    "phase6_1_riverbank_audit": {
        "phase": "Phase 6.1",
        "title": "Riverbank Geometry Audit, Cross-Phase Reconciliation & Scientific Validation",
        "category": "Geomorphology Audit",
        "filename": "phase6_1_riverbank_audit_report.json",
    },
    "phase6_2_uncertainty_audit": {
        "phase": "Phase 6.2",
        "title": "Displacement Uncertainty, Statistical Confidence & Scientific Readiness Audit",
        "category": "Statistical Uncertainty Analysis",
        "filename": "phase6_2_uncertainty_audit.json",
    },
    "phase7a_random_forest": {
        "phase": "Phase 7A",
        "title": "SAR-Based Random Forest Development, Training & Scientific Evaluation",
        "category": "Machine Learning",
        "filename": "phase7a_model_report.json",
    },
    "phase7b_explainability": {
        "phase": "Phase 7B",
        "title": "Explainable AI, Tree-Path Attribution & SAR Model Interpretability",
        "category": "Explainable AI",
        "filename": "phase7b_explainability_report.json",
    },
    "phase7b1_integrity_audit": {
        "phase": "Phase 7B.1",
        "title": "Tree Explainability Mathematical Verification & Random Forest Integrity Audit",
        "category": "Algorithm & Model Verification",
        "filename": "phase7b1_integrity_audit.json",
    },
    "phase7b1_backend_errata": {
        "phase": "Phase 7B.1 / Phase 8",
        "title": "Phase 7B.1 Errata & Authoritative Backend Metadata Corrections",
        "category": "Data Governance Errata",
        "filename": "phase7b1_backend_errata.json",
    },
}


class ReportService:
    @staticmethod
    def list_reports() -> List[Dict[str, Any]]:
        results = []
        for r_id, info in REPORT_CATALOG.items():
            fpath = settings.METADATA_DIR / info["filename"]
            exists = fpath.exists()
            results.append({
                "report_id": r_id,
                "phase": info["phase"],
                "title": info["title"],
                "category": info["category"],
                "filename": info["filename"],
                "format": "JSON",
                "status": "AVAILABLE" if exists else "NOT_FOUND",
                "deliverables_count": 1 if exists else 0,
            })
        return results

    @staticmethod
    def _lookup_report(report_id: str) -> Optional[Tuple[str, Dict[str, str]]]:
        if report_id in REPORT_CATALOG:
            return report_id, REPORT_CATALOG[report_id]
        for k, v in REPORT_CATALOG.items():
            if report_id in k or k in report_id:
                return k, v
        return None

    @classmethod
    def get_report_detail(cls, report_id: str) -> Optional[Dict[str, Any]]:
        lookup = cls._lookup_report(report_id)
        if not lookup:
            return None
        resolved_id, info = lookup

        fpath = settings.METADATA_DIR / info["filename"]
        if not fpath.exists():
            return None

        with open(fpath, "r") as f:
            data = json.load(f)

        return {
            "report_id": resolved_id,
            "title": info["title"],
            "phase": info["phase"],
            "metadata": data,
            "summary_findings": {
                "phase": info["phase"],
                "category": info["category"],
                "status": "OFFICIALLY_REGISTERED",
            },
            "associated_artifacts": [info["filename"]],
        }

    @staticmethod
    def get_region_statistics(region_id: str) -> Dict[str, Any]:
        return {
            "region_id": region_id,
            "summary_timestamp": "2026-11-04T00:00:00Z",
            "flood_statistics": {
                "pre_monsoon_water_ha": 8733.20,
                "monsoon_crest_water_ha": 15185.44,
                "net_water_expansion_ha": 5814.32,
                "persistent_water_ha": 8719.12,
                "newly_inundated_candidate_ha": 6452.24,
                "receded_water_ha": 14.08,
            },
            "riverbank_statistics": {
                "mean_west_displacement_m": 130.00,
                "mean_east_displacement_m": 160.66,
                "mean_channel_width_change_m": 290.66,
                "detection_threshold_range_m": "35-85m",
                "audited_valid_transects": 122,
            },
            "model_statistics": {
                "model_identifier": "phase7a_rf_jamuna_v1",
                "model_status": "RETAINED_AS_PROBABILITY_LAYER",
                "optimal_threshold": 0.35,
                "test_f1_score": 0.6026,
                "test_recall": 0.9214,
                "test_precision": 0.4477,
                "brier_score": 0.2270,
                "ece": 0.0959,
            },
            "optical_validation_agreement_pct": 64.68,
            "authoritative_baseline_agreement_pct": 53.89,
        }
