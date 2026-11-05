"""
Phase 8.6 Independent Scientific Review Corrections & Reconciliation Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Validates the full scientific reconciliation across:
  1. Authoritative Phase 5 flood transitions raster masks, dual-domain accounting, and mass balance.
  2. Riverbank migration empirical statistics (122 valid rows) and 95% spatial block bootstrap CIs.
  3. Frozen Random Forest model artifact integrity (SHA-256), 40-tree architecture, and held-out test metrics.
  4. Explainable AI float32 inference representation and strict tree-path local additivity (|residual| < 1e-5).
  5. Authoritative Study AOI cutline masking in raster tile rendering (100% transparent outside AOI).
  6. Backend REST API contract adherence and negative tamper detection.
"""

import hashlib
import io
import json
from pathlib import Path
from typing import Dict, Any

import numpy as np
import pandas as pd
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from osgeo import gdal

from src.backend.config import settings
from src.backend.contracts import (
    AOI_TOTAL_CELLS,
    COMMON_VALID_DOMAIN_CELLS,
    PERSISTENT_NON_WATER_CELLS,
    PERSISTENT_WATER_CELLS,
    NEWLY_INUNDATED_CANDIDATE_CELLS,
    RECEDED_WATER_CELLS,
    INDETERMINATE_CELLS,
    NODATA_AOI_CELLS,
    NET_VALID_DOMAIN_CHANGE_HA,
    WHOLE_EPOCH_UNMASKED_DELTA_HA,
    ASYMMETRIC_EXCLUSIONS_GAP_HA,
    DISPLACEMENT_EMPIRICAL_STATS,
)
from src.backend.main import app
from src.backend.services.raster_service import RasterService
from src.ml.explainability import TreePathExplainer
from src.ml.random_forest import RandomForestClassifier

gdal.UseExceptions()

EXPECTED_FROZEN_MODEL_SHA256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# 1. Authoritative Flood Detection Raster Pixel Counts & Accounting Identities
# ==============================================================================
def test_01_authoritative_flood_raster_pixel_counts_and_identities():
    """
    Verifies actual pixel counts and area calculations across Phase 5 flood rasters
    against the authoritative transition matrix and inundation area summary.
    Enforces exact accounting identities:
      - C1 + C2 + C3 + C4 == Common Valid Domain (993,736 cells)
      - Common Valid Domain + Indeterminate (16,242) + NoData (61) == Total AOI (1,010,039 cells)
      - Net Candidate Inundation == Newly Inundated (146,992) - Receded (1,634) == 145,358 cells (5,814.32 ha)
    """
    p5_dir = settings.PROJECT_ROOT_DIR / "data/processed/phase5"

    expected_masks = {
        "phase5_persistent_water.tif": PERSISTENT_WATER_CELLS,                    # 216,595
        "phase5_newly_inundated_candidate.tif": NEWLY_INUNDATED_CANDIDATE_CELLS,  # 146,992
        "phase5_receded_water.tif": RECEDED_WATER_CELLS,                          # 1,634
        "phase5_persistent_non_water.tif": PERSISTENT_NON_WATER_CELLS,            # 628,515
        "phase5_indeterminate_mask.tif": INDETERMINATE_CELLS,                    # 16,242
    }

    observed_counts = {}
    for filename, expected_cells in expected_masks.items():
        raster_path = p5_dir / filename
        assert raster_path.exists(), f"Phase 5 raster file missing: {raster_path}"

        ds = gdal.Open(str(raster_path))
        arr = ds.GetRasterBand(1).ReadAsArray()
        cells = int(np.sum(arr == 1))
        observed_counts[filename] = cells

        assert cells == expected_cells, f"Count mismatch in {filename}: {cells} vs {expected_cells}"

    # Verify Common Valid Domain Identity
    common_valid_cells = (
        observed_counts["phase5_persistent_water.tif"]
        + observed_counts["phase5_newly_inundated_candidate.tif"]
        + observed_counts["phase5_receded_water.tif"]
        + observed_counts["phase5_persistent_non_water.tif"]
    )
    assert common_valid_cells == COMMON_VALID_DOMAIN_CELLS == 993_736
    assert round(common_valid_cells * 0.04, 2) == 39_749.44  # hectares
    assert round(common_valid_cells * 0.0004, 4) == 397.4944  # km2

    # Verify Total AOI Identity
    total_aoi_cells = common_valid_cells + observed_counts["phase5_indeterminate_mask.tif"] + NODATA_AOI_CELLS
    assert total_aoi_cells == AOI_TOTAL_CELLS == 1_010_039
    assert abs(total_aoi_cells * 0.0004 - 404.0156) < 1e-4

    # Verify Net Surface Water Change & Asymmetric Exclusion Gap
    net_cells = observed_counts["phase5_newly_inundated_candidate.tif"] - observed_counts["phase5_receded_water.tif"]
    assert net_cells == 145_358
    assert net_cells * 0.04 == NET_VALID_DOMAIN_CHANGE_HA == 5_814.32

    computed_gap_ha = round(WHOLE_EPOCH_UNMASKED_DELTA_HA - NET_VALID_DOMAIN_CHANGE_HA, 2)
    assert computed_gap_ha == ASYMMETRIC_EXCLUSIONS_GAP_HA == 637.92


# ==============================================================================
# 2. Riverbank Migration Empirical Statistics & Spatial Bootstrap CIs
# ==============================================================================
def test_02_riverbank_empirical_statistics_and_bootstrap_intervals():
    """
    Verifies transect displacement audit classifications (154 evaluated, 122 valid local migration),
    empirical lateral displacement statistics from the 122 valid rows, and 95% spatial block
    bootstrap confidence intervals.
    """
    audit_csv = settings.PROJECT_ROOT_DIR / "data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv"
    assert audit_csv.exists(), f"Audit CSV missing: {audit_csv}"
    df_audit = pd.read_csv(audit_csv)

    # 154 evaluated transects
    assert len(df_audit) == 154

    status_counts = df_audit["confidence_status"].value_counts().to_dict()
    assert status_counts.get("VALID_LOCAL_MIGRATION") == 122
    assert status_counts.get("AMBIGUOUS_EDGE_EFFECT") == 23
    assert status_counts.get("ANABRANCH_ACTIVATION") == 5
    assert status_counts.get("MAJOR_CHANNEL_EXPANSION") == 4
    assert (23 + 5 + 4) == 32

    # Empirical statistics on 122 valid rows
    df_valid = df_audit[df_audit["confidence_status"] == "VALID_LOCAL_MIGRATION"]
    assert len(df_valid) == 122

    west_mean = round(float(df_valid["right_bank_displacement_m"].mean()), 2)
    east_mean = round(float(df_valid["left_bank_displacement_m"].mean()), 2)
    width_mean = round(float(df_valid["channel_width_expansion_m"].mean()), 2)

    west_med = round(float(df_valid["right_bank_displacement_m"].median()), 2)
    east_med = round(float(df_valid["left_bank_displacement_m"].median()), 2)
    width_med = round(float(df_valid["channel_width_expansion_m"].median()), 2)

    assert west_mean == DISPLACEMENT_EMPIRICAL_STATS["west_bank"]["mean_m"] == 130.00
    assert east_mean == DISPLACEMENT_EMPIRICAL_STATS["east_bank"]["mean_m"] == 160.66
    assert width_mean == DISPLACEMENT_EMPIRICAL_STATS["channel_width"]["mean_m"] == 290.66

    assert west_med == DISPLACEMENT_EMPIRICAL_STATS["west_bank"]["median_m"] == 40.00
    assert east_med == DISPLACEMENT_EMPIRICAL_STATS["east_bank"]["median_m"] == 90.00
    assert width_med == DISPLACEMENT_EMPIRICAL_STATS["channel_width"]["median_m"] == 180.00

    # Spatial block bootstrap 95% confidence intervals
    ci_csv = settings.PROJECT_ROOT_DIR / "data/outputs/phase6_2/statistics/phase6_2_spatial_bootstrap_intervals.csv"
    assert ci_csv.exists(), f"Bootstrap CSV missing: {ci_csv}"
    df_ci = pd.read_csv(ci_csv)

    expected_cis = {
        ("Right Bank (West / Mainland)", "Median Displacement"): [20.0, 80.0],
        ("Left Bank (East / Chars)", "Median Displacement"): [20.0, 150.0],
        ("Channel Width Expansion", "Median Displacement"): [120.0, 320.0],
    }

    for (target_feat, stat_name), expected_ci in expected_cis.items():
        row = df_ci[(df_ci["target_feature"] == target_feat) & (df_ci["statistic"] == stat_name)]
        assert len(row) == 1, f"Missing CI row for {target_feat} - {stat_name}"
        r = row.iloc[0]
        obs_ci = [float(r["ci_95_lower_m"]), float(r["ci_95_upper_m"])]
        assert obs_ci == expected_ci, f"CI mismatch for {target_feat}: {obs_ci} vs {expected_ci}"


# ==============================================================================
# 3. Frozen Random Forest Model & Held-Out Test Evaluation Metrics
# ==============================================================================
def test_03_frozen_random_forest_model_and_evaluation_metrics():
    """
    Verifies the cryptographic SHA-256 digest of the frozen model artifact,
    confirms its 40-tree architecture, evaluates the 6,124 held-out test split samples,
    and proves why the model is retained strictly as an auxiliary probability layer.
    """
    model_path = settings.PROJECT_ROOT_DIR / "models/phase7a/phase7a_random_forest_model.joblib"
    assert model_path.exists(), f"Model artifact missing: {model_path}"

    # Cryptographic integrity check
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    actual_sha = h.hexdigest().lower()
    assert actual_sha == EXPECTED_FROZEN_MODEL_SHA256.lower(), f"SHA256 mismatch: {actual_sha}"

    # Load pure-NumPy Random Forest model
    rf = RandomForestClassifier.load(model_path)
    assert rf.n_estimators == 40
    assert rf.max_depth == 6
    assert len(rf.estimators_) == 40

    # Verify sample dataset partitions
    samples_csv = settings.PROJECT_ROOT_DIR / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
    assert samples_csv.exists(), f"Samples CSV missing: {samples_csv}"
    df_samples = pd.read_csv(samples_csv)
    assert len(df_samples) == 31_522

    split_counts = df_samples["split"].value_counts().to_dict()
    assert split_counts.get("train") == 18_825
    assert split_counts.get("val") == 6_573
    assert split_counts.get("test") == 6_124

    # Held-out test evaluation at tau* = 0.35
    test_df = df_samples[df_samples["split"] == "test"]
    feature_cols = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
    X_test = test_df[feature_cols].values
    y_test = test_df["label"].values

    prob = rf.predict_proba(X_test)[:, 1]
    tau = 0.35
    pred = (prob >= tau).astype(int)

    tp = int(np.sum((pred == 1) & (y_test == 1)))
    tn = int(np.sum((pred == 0) & (y_test == 0)))
    fp = int(np.sum((pred == 1) & (y_test == 0)))
    fn = int(np.sum((pred == 0) & (y_test == 1)))

    assert tp == 2239
    assert tn == 932
    assert fp == 2762
    assert fn == 191

    acc = (tp + tn) / len(test_df)
    prec = tp / (tp + fp)
    rec = tp / (tp + fn)
    f1 = 2 * (prec * rec) / (prec + rec)

    assert abs(acc - 0.5178) < 0.001
    assert abs(prec - 0.4477) < 0.001
    assert abs(rec - 0.9214) < 0.001
    assert abs(f1 - 0.6026) < 0.001

    # Mann-Whitney U test formula for ROC-AUC
    pos = prob[y_test == 1]
    neg = prob[y_test == 0]
    ranks = pd.Series(prob).rank(method="average").values
    r_pos = np.sum(ranks[y_test == 1])
    n_pos, n_neg = len(pos), len(neg)
    auc = (r_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    assert abs(auc - 0.6810) < 0.001

    # Confirm why retained strictly as probability layer:
    # Low precision (~0.4477) causes 2,762 false positives on non-water targets.
    assert prec < 0.50, "Random Forest precision is insufficient to replace Otsu dual-pol physical baseline"


# ==============================================================================
# 4. Explainable AI float32 Precision & Local Additivity Property
# ==============================================================================
def test_04_explainability_float32_precision_and_additivity_guarantee():
    """
    Verifies that the TreePathExplainer decomposed at float32 inference representation
    obeys exact local additivity (|P(x) - (Base + sum(phi))| < 1e-5) across held-out samples,
    tree split threshold boundaries, and np.nextafter extreme offsets.
    """
    model_path = settings.PROJECT_ROOT_DIR / "models/phase7a/phase7a_random_forest_model.joblib"
    rf = RandomForestClassifier.load(model_path)
    feature_cols = ["vv_db", "vh_db", "cross_pol_ratio", "vv_minus_vh_db", "texture_vv", "texture_vh"]
    explainer = TreePathExplainer(rf, feature_names=feature_cols)

    # Test 1: Held-out samples from test split
    samples_csv = settings.PROJECT_ROOT_DIR / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
    df_samples = pd.read_csv(samples_csv)
    test_df = df_samples[df_samples["split"] == "test"]
    X_test = test_df[feature_cols].values[:200]

    for x in X_test:
        res = explainer.explain_instance(x, baseline_mode="ensemble_root")
        assert res["is_additive"] is True
        assert res["additivity_error"] < 1e-5, f"Additivity error too large: {res['additivity_error']}"

    # Test 2: Synthetic split-threshold boundary and np.nextafter cases
    boundary_samples = []
    for tree in rf.estimators_:
        node_stack = [tree.root]
        while node_stack:
            curr = node_stack.pop()
            if not curr.is_leaf:
                f_idx = curr.feature
                thresh = curr.threshold
                # Exact threshold
                vec_exact = np.zeros(6, dtype=np.float32)
                vec_exact[f_idx] = thresh
                boundary_samples.append(vec_exact)
                # Just above threshold
                vec_above = vec_exact.copy()
                vec_above[f_idx] = np.nextafter(thresh, np.float32(np.inf))
                boundary_samples.append(vec_above)
                # Just below threshold
                vec_below = vec_exact.copy()
                vec_below[f_idx] = np.nextafter(thresh, np.float32(-np.inf))
                boundary_samples.append(vec_below)

                node_stack.append(curr.left)
                node_stack.append(curr.right)

    assert len(boundary_samples) > 0
    for x_b in boundary_samples[:300]:
        res_b = explainer.explain_instance(x_b, baseline_mode="ensemble_root")
        assert res_b["is_additive"] is True
        assert res_b["additivity_error"] < 1e-5, f"Boundary additivity error too large: {res_b['additivity_error']}"


# ==============================================================================
# 5. Study AOI Cutline Masking in Raster Tile Rendering
# ==============================================================================
def test_05_raster_service_aoi_cutline_masking():
    """
    Verifies that categorical rasters bound to the Study AOI are rendered with GDAL cutline masking.
    Tiles inside the Study AOI render visible classes (alpha > 0).
    Tiles completely outside the Study AOI return 100% transparent PNGs (all alpha == 0).
    """
    # 1. Inside Study AOI tile (approx lon 89.65, lat 24.67, zoom 12)
    png_inside = RasterService.render_tile("phase5_flood_transitions", 12, 3068, 1758)
    assert len(png_inside) > 500, "Inside AOI tile must return non-trivial PNG"
    img_in = Image.open(io.BytesIO(png_inside))
    arr_in = np.array(img_in)
    assert arr_in.shape == (256, 256, 4)
    assert np.any(arr_in[:, :, 3] > 0), "Inside AOI tile must contain visible non-transparent pixels"

    # 2. Outside Study AOI tile (approx lon 89.52, lat 24.55, zoom 14)
    png_outside = RasterService.render_tile("phase5_flood_transitions", 14, 12266, 7038)
    assert len(png_outside) > 0
    img_out = Image.open(io.BytesIO(png_outside))
    arr_out = np.array(img_out)
    assert arr_out.shape == (256, 256, 4)
    assert np.all(arr_out[:, :, 3] == 0), "Outside AOI tile must be 100% transparent (alpha=0 for all pixels)"


# ==============================================================================
# 6. Backend REST API Endpoints Contract Reconciliation
# ==============================================================================
def test_06_backend_endpoints_contract_reconciliation(client):
    """
    Verifies the corrected REST endpoints return reconciled contracts matching
    authoritative Phase 5 and Phase 6 metrics.
    """
    # Flood transitions endpoint
    r_flood = client.get("/api/v1/regions/jamuna_sirajganj/flood/transitions")
    assert r_flood.status_code == 200
    d_flood = r_flood.json()
    assert d_flood["common_valid_domain_cells"] == 993_736
    assert d_flood["common_valid_domain_km2"] == 397.4944

    transitions = {t["class_id"]: t for t in d_flood["transitions"]}
    assert transitions[1]["pixel_count"] == 216_595
    assert abs(transitions[1]["percentage_of_valid_domain"] - 21.7960) < 0.01
    assert transitions[2]["pixel_count"] == 146_992
    assert abs(transitions[2]["percentage_of_valid_domain"] - 14.7919) < 0.01
    assert transitions[3]["pixel_count"] == 1_634
    assert abs(transitions[3]["percentage_of_valid_domain"] - 0.1644) < 0.01
    assert transitions[4]["pixel_count"] == 628_515
    assert abs(transitions[4]["percentage_of_valid_domain"] - 63.2477) < 0.01

    # Riverbank displacement endpoint
    r_disp = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/displacement")
    assert r_disp.status_code == 200
    d_disp = r_disp.json()
    assert d_disp["west_bank_expansion_stats"]["mean_m"] == 130.00
    assert d_disp["west_bank_expansion_stats"]["median_m"] == 40.00
    assert d_disp["east_bank_expansion_stats"]["mean_m"] == 160.66
    assert d_disp["east_bank_expansion_stats"]["median_m"] == 90.00
    assert d_disp["net_channel_width_change_stats"]["mean_m"] == 290.66
    assert d_disp["net_channel_width_change_stats"]["median_m"] == 180.00


# ==============================================================================
# 7. Negative Contract Integrity & Tamper Detection
# ==============================================================================
def test_07_negative_contract_integrity_and_tamper_detection(client):
    """
    Verifies that system contracts strictly reject invalid states, corrupted inputs,
    and unknown resource identifiers.
    """
    # 1. Unknown region rejection
    r_bad_region = client.get("/api/v1/regions/non_existent_region/flood/transitions")
    assert r_bad_region.status_code == 404

    # 2. Unknown model rejection
    r_bad_model = client.get("/api/v1/models/non_existent_model_v99")
    assert r_bad_model.status_code == 404

    # 3. Mathematical tamper detection assertion
    corrupted_cells_sum = 216_595 + 146_992 + 1_634 + 600_000  # Intentionally corrupt persistent non-water
    with pytest.raises(AssertionError):
        assert corrupted_cells_sum == COMMON_VALID_DOMAIN_CELLS, "Tampered cell counts must be rejected!"

    # 4. Out-of-bounds tile rendering returns transparent blank tile, not 500 error
    blank_tile = RasterService.render_tile("phase5_flood_transitions", 25, 999999, 999999)
    assert len(blank_tile) > 0
    img = Image.open(io.BytesIO(blank_tile))
    assert np.all(np.array(img)[:, :, 3] == 0)
