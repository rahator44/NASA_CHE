"""
Earth Pulse SQLite Persistence & Job Management Database
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.backend.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Provides a SQLite database connection with row factory enabled, auto-initializing schema if needed."""
    settings.SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_exists = settings.SQLITE_DB_PATH.exists()
    conn = sqlite3.connect(str(settings.SQLITE_DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    
    # Check if table exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    if not cursor.fetchone():
        _create_tables_and_seed(conn)
        
    return conn


def init_db() -> None:
    """Explicitly initializes SQLite schema for jobs, analysis runs, and system provenance."""
    with sqlite3.connect(str(settings.SQLITE_DB_PATH), timeout=20.0) as conn:
        _create_tables_and_seed(conn)


def _create_tables_and_seed(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    # Jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            region_id TEXT NOT NULL,
            parameters TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_pct REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_summary TEXT,
            output_references TEXT,
            provenance_links TEXT
        )
    """)
    
    # Analysis runs catalog table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            analysis_type TEXT NOT NULL,
            region_id TEXT NOT NULL,
            status TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            completed_at TEXT,
            parameters TEXT,
            outputs TEXT,
            metadata TEXT
        )
    """)
    conn.commit()
    _seed_precomputed_analysis_runs(conn)


def _seed_precomputed_analysis_runs(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    
    runs = [
        (
            "run_phase1_alignment",
            "SAR_COREGISTRATION_ALIGNMENT",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-10-31T23:18:00Z",
            "2024-10-31T23:18:30Z",
            json.dumps({"grid": "EPSG:32645", "spacing_m": 20.0}),
            json.dumps({"aligned_june10": "data/processed/aligned/june10_aligned.tif", "aligned_july16": "data/processed/aligned/july16_aligned.tif"}),
            json.dumps({"rmse_x_px": 0.038, "rmse_y_px": 0.037, "status": "VERIFIED_SUB_PIXEL"})
        ),
        (
            "run_phase2a_backscatter",
            "CALIBRATED_BACKSCATTER_DELTA",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-10-31T23:42:00Z",
            "2024-10-31T23:42:25Z",
            json.dumps({"polarizations": ["VV", "VH"], "delta_mode": "july_minus_june_db"}),
            json.dumps({"delta_vv": "data/processed/phase2a/delta_vv_db.tif", "delta_vh": "data/processed/phase2a/delta_vh_db.tif"}),
            json.dumps({"mean_vv_june_db": -10.96, "mean_vv_july_db": -12.44, "mean_delta_vv_db": -1.48})
        ),
        (
            "run_phase2b_filtering",
            "ADAPTIVE_SPECKLE_FILTERING",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-01T00:30:00Z",
            "2024-11-01T00:30:45Z",
            json.dumps({"filter_window": "5x5", "filter_type": "Lee", "damp_factor": 1}),
            json.dumps({"lee5x5_june": "data/processed/phase2b/lee_5x5/june10_lee_5x5.tif", "lee5x5_july": "data/processed/phase2b/lee_5x5/july16_lee_5x5.tif"}),
            json.dumps({"enl_improvement_factor": 2.68, "edge_blur_penalty_pct": 2.1})
        ),
        (
            "run_phase3a_water_classification",
            "ADAPTIVE_OTSU_WATER_CLASSIFICATION",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-01T09:49:00Z",
            "2024-11-01T09:49:35Z",
            json.dumps({"rule": "Dual-AND (sigma0_VV < T_vv) AND (sigma0_VH < T_vh)", "filter": "lee_5x5"}),
            json.dumps({"june_mask": "data/processed/phase3a/candidate_masks/june10_lee_5x5_otsu_dual_and.tif", "july_mask": "data/processed/phase3a/candidate_masks/july16_lee_5x5_otsu_dual_and.tif"}),
            json.dumps({"june_water_area_ha": 8733.20, "july_water_area_ha": 15185.44, "june_thresh_vv": -12.457, "june_thresh_vh": -21.697, "july_thresh_vv": -14.960, "july_thresh_vh": -21.828})
        ),
        (
            "run_phase5_flood_change",
            "FINAL_FLOOD_CHANGE_ENGINE",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-02T13:46:00Z",
            "2024-11-02T13:46:40Z",
            json.dumps({"methodology": "Dual-AND Otsu with Common-Valid-Domain accounting"}),
            json.dumps({"transitions_raster": "data/processed/phase5/phase5_flood_transitions.tif", "clusters_geojson": "data/outputs/phase5/maps/phase5_major_inundation_clusters.geojson"}),
            json.dumps({"persistent_water_ha": 8663.80, "newly_inundated_ha": 5879.68, "receded_water_ha": 65.36, "net_change_ha": 5814.32, "whole_epoch_delta_ha": 6452.24})
        ),
        (
            "run_phase6_riverbank_migration",
            "RIVERBANK_MIGRATION_ANALYSIS",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-02T15:18:00Z",
            "2024-11-02T15:18:45Z",
            json.dumps({"transect_spacing_m": 200, "total_transects": 154, "valid_transects": 122, "outside_valid_transects": 32}),
            json.dumps({"transects_geojson": "data/outputs/phase6_1/maps/phase6_1_riverbank_transects.geojson", "zones_raster": "data/processed/phase6_1/phase6_1_channel_change_zones.tif"}),
            json.dumps({"mean_west_displacement_m": 126.39, "mean_east_displacement_m": 157.38, "mean_width_change_m": 283.77, "detection_range_m": "35-85m"})
        ),
        (
            "run_phase7a_random_forest",
            "SAR_RANDOM_FOREST_TRAINING",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-03T22:24:00Z",
            "2024-11-03T22:25:10Z",
            json.dumps({"n_estimators": 40, "max_depth": 6, "threshold": 0.35, "status": "RETAINED_AS_PROBABILITY_LAYER"}),
            json.dumps({"model_joblib": "models/phase7a/phase7a_random_forest_model.joblib", "water_prob_july": "data/processed/phase7a/phase7a_july16_water_probability.tif"}),
            json.dumps({"test_accuracy": 0.5178, "test_recall": 0.9214, "test_precision": 0.4477, "roc_auc": 0.6810})
        ),
        (
            "run_phase7b_explainability",
            "EXPLAINABLE_AI_TREE_PATH_ATTRIBUTION",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-03T23:28:00Z",
            "2024-11-03T23:29:15Z",
            json.dumps({"engine": "Pure-NumPy TreePathExplainer (Saabas Formulation)", "features_count": 6}),
            json.dumps({"local_csv": "data/outputs/phase7b/local_explanations/phase7b_local_prediction_explanations.csv", "global_csv": "data/outputs/phase7b/shap/phase7b_global_shap_importance.csv"}),
            json.dumps({"rank1_feature": "vv_db", "rank2_feature": "vh_db", "grouped_backscatter_pct": 67.38, "brier_score": 0.2270, "ece": 0.0959})
        ),
        (
            "run_phase7b1_integrity_audit",
            "MODEL_INTEGRITY_MATHEMATICAL_VERIFICATION",
            "jamuna_sirajganj",
            "COMPLETED",
            "2024-11-03T23:55:00Z",
            "2024-11-03T23:55:30Z",
            json.dumps({"audit_tasks": ["A", "B", "C", "D", "E", "F", "G", "H", "I"]}),
            json.dumps({"audit_csvs_dir": "data/outputs/phase7b1/audit/", "audit_json": "data/metadata/phase7b1_integrity_audit.json"}),
            json.dumps({"verified_test_count": 291, "additivity_error": "< 1e-8", "bruteforce_shapley_verified": True})
        )
    ]
    
    cursor.executemany("""
        INSERT OR REPLACE INTO analysis_runs 
        (run_id, analysis_type, region_id, status, executed_at, completed_at, parameters, outputs, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, runs)
    conn.commit()
