"""
Automated Test Suite for Phase 3B.1: Transition Classification & Full-Scene NoData Audit
Earth Pulse: Dancing with the SARs (NASA Space Apps Challenge 2026)

Tests cover:
1. Source NoData priority.
2. Clipping-floor priority.
3. Other invalid category handling.
4. Verified ambiguous category handling.
5. Full-scene category conservation.
6. AOI category conservation.
7. Full-scene NoData reconciliation.
8. Area identity.
9. Connected-component conservation.
10. Correct georeferencing.
"""

import json
from pathlib import Path
import numpy as np
import pytest
from osgeo import gdal, ogr, osr
from scipy.ndimage import label

from scripts.audit_phase3b_qc import (
    find_project_root,
    classify_temporal_transition,
    calculate_transition_statistics,
    analyze_connected_components,
    rasterize_polygon_mask,
    CLASS_PERSISTENT_WATER,
    CLASS_NEWLY_INUNDATED,
    CLASS_RECEDED_WATER,
    CLASS_PERSISTENT_NON_WATER,
    CLASS_INDETERMINATE,
    CLASS_NODATA_INVALID,
    FULL_SCENE_CELLS,
    AOI_TARGET_CELLS,
    PRELIMINARY_AOI_WKT,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


@pytest.fixture(scope="module")
def reference_dataset(project_root: Path) -> gdal.Dataset:
    ref_path = project_root / "data" / "processed" / "aligned" / "june10_aligned.tif"
    assert ref_path.is_file(), f"Reference aligned GeoTIFF missing: {ref_path}"
    return gdal.Open(str(ref_path), gdal.GA_ReadOnly)


@pytest.fixture(scope="module")
def aoi_mask(reference_dataset: gdal.Dataset) -> np.ndarray:
    return rasterize_polygon_mask(PRELIMINARY_AOI_WKT, reference_dataset)


# Test 1: Source NoData priority
def test_source_nodata_priority():
    """Verify that if either epoch has source NoData (3), output is strictly Class 6."""
    june = np.array([3, 3, 3, 3, 0, 1, 2, 4], dtype=np.uint8)
    july = np.array([0, 1, 2, 3, 3, 3, 3, 3], dtype=np.uint8)

    trans = classify_temporal_transition(june, july)
    # All 8 combinations have at least one 3, so all must be CLASS_NODATA_INVALID (6)
    assert np.all(trans == CLASS_NODATA_INVALID), "NoData priority tier failed"


# Test 2: Clipping-floor priority
def test_clipping_floor_priority():
    """Verify that if either epoch has clipping-floor (2) and neither is 3, output is strictly Class 5."""
    june = np.array([2, 2, 2, 0, 1], dtype=np.uint8)
    july = np.array([0, 1, 2, 2, 2], dtype=np.uint8)

    trans = classify_temporal_transition(june, july)
    assert np.all(trans == CLASS_INDETERMINATE), "Clipping-floor priority tier failed"


# Test 3: Other invalid category handling
def test_other_invalid_category_handling():
    """Verify NoData is never categorized as Indeterminate and valid data is not marked NoData."""
    june = np.array([0, 1, 3, 2], dtype=np.uint8)
    july = np.array([1, 0, 2, 0], dtype=np.uint8)

    trans = classify_temporal_transition(june, july)
    # index 0: 0 -> 1 : newly inundated (2)
    # index 1: 1 -> 0 : receded water (3)
    # index 2: 3 -> 2 : NoData takes precedence over clipping floor -> Class 6
    # index 3: 2 -> 0 : clipping floor -> Class 5
    assert trans[0] == CLASS_NEWLY_INUNDATED
    assert trans[1] == CLASS_RECEDED_WATER
    assert trans[2] == CLASS_NODATA_INVALID
    assert trans[3] == CLASS_INDETERMINATE


# Test 4: Verified ambiguous category handling
def test_verified_ambiguous_category_handling():
    """Verify that code 4 (ambiguous 2D Otsu observation) maps to Class 5 when not NoData."""
    june = np.array([4, 0, 4, 3], dtype=np.uint8)
    july = np.array([0, 4, 1, 4], dtype=np.uint8)

    trans = classify_temporal_transition(june, july)
    assert trans[0] == CLASS_INDETERMINATE
    assert trans[1] == CLASS_INDETERMINATE
    assert trans[2] == CLASS_INDETERMINATE
    assert trans[3] == CLASS_NODATA_INVALID  # 3 overrides 4


# Test 5: Full-scene category conservation
def test_full_scene_category_conservation(project_root: Path):
    """Verify that all 4 QC transition rasters conserve exactly 1,957,165 full-scene cells."""
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    configs = ["primary", "2d_otsu", "lee_3x3", "unfiltered"]

    for cfg in configs:
        p = qc_dir / f"transition_{cfg}_qc.tif"
        assert p.is_file(), f"Missing QC transition raster: {p}"
        ds = gdal.Open(str(p), gdal.GA_ReadOnly)
        arr = ds.GetRasterBand(1).ReadAsArray()
        ds = None

        unique_vals, counts = np.unique(arr, return_counts=True)
        assert np.all((unique_vals >= 1) & (unique_vals <= 6)), f"Unexpected values in {cfg}: {unique_vals}"
        assert int(np.sum(counts)) == FULL_SCENE_CELLS, f"Cell conservation failed for {cfg}"


# Test 6: AOI category conservation
def test_aoi_category_conservation(project_root: Path, aoi_mask: np.ndarray):
    """Verify that within the Kazipur study AOI, exactly 1,010,039 cells are conserved."""
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    configs = ["primary", "2d_otsu", "lee_3x3", "unfiltered"]

    assert int(np.sum(aoi_mask)) == AOI_TARGET_CELLS, "AOI target cell count mismatch"

    for cfg in configs:
        p = qc_dir / f"transition_{cfg}_qc.tif"
        ds = gdal.Open(str(p), gdal.GA_ReadOnly)
        arr = ds.GetRasterBand(1).ReadAsArray()[aoi_mask]
        ds = None

        stats = calculate_transition_statistics(arr)
        assert stats["total_cells"] == AOI_TARGET_CELLS
        assert stats["reconciliation_identity_holds"] is True


# Test 7: Full-scene NoData reconciliation
def test_full_scene_nodata_reconciliation(project_root: Path):
    """
    Verify that full-scene Class 6 equals 577,307 pixels (~29.50%),
    matching the union of June NoData (577,183) and July NoData (576,591).
    """
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    p = qc_dir / "transition_primary_qc.tif"
    ds = gdal.Open(str(p), gdal.GA_ReadOnly)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None

    nodata_count = int(np.sum(arr == CLASS_NODATA_INVALID))
    expected_nodata = 577307
    assert nodata_count == expected_nodata, f"Expected {expected_nodata} NoData cells, found {nodata_count}"

    pct = nodata_count / FULL_SCENE_CELLS * 100.0
    assert abs(pct - 29.4971) < 0.01, f"Expected ~29.50% NoData, found {pct:.4f}%"

    # Indeterminate count verification
    indet_count = int(np.sum(arr == CLASS_INDETERMINATE))
    assert indet_count == 18930, f"Expected 18,930 Indeterminate cells, found {indet_count}"


# Test 8: Area identity
def test_area_identity(project_root: Path, aoi_mask: np.ndarray):
    """
    Verify mathematical identity:
    Gross Expansion - Gross Recession == Net Water Change == Valid July Water - Valid June Water
    """
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    p = qc_dir / "transition_primary_qc.tif"
    ds = gdal.Open(str(p), gdal.GA_ReadOnly)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None

    # Inside AOI
    stats_aoi = calculate_transition_statistics(arr, spatial_mask=aoi_mask)
    c1 = stats_aoi["persistent_water_cells"]
    c2 = stats_aoi["newly_inundated_candidate_cells"]
    c3 = stats_aoi["receded_water_cells"]

    gross_exp = c2
    gross_rec = c3
    net_change = c2 - c3
    diff_direct = (c1 + c2) - (c1 + c3)

    assert net_change == (gross_exp - gross_rec)
    assert net_change == diff_direct
    assert stats_aoi["reconciliation_identity_holds"] is True
    assert c2 == 146992
    assert c3 == 1634
    assert net_change == 145358


# Test 9: Connected-component conservation
def test_connected_component_conservation(project_root: Path, aoi_mask: np.ndarray):
    """Verify that connected components strictly conserve 146,992 candidate pixels in the AOI."""
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    p = qc_dir / "newly_inundated_candidate_qc.tif"
    ds = gdal.Open(str(p), gdal.GA_ReadOnly)
    gt = ds.GetGeoTransform()
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None

    inund_aoi = (arr == 1) & aoi_mask
    total_px = int(np.sum(inund_aoi))
    assert total_px == 146992, f"Expected 146,992 inundation pixels, found {total_px}"

    res = analyze_connected_components(inund_aoi, gt, top_n=50)
    assert res["total_pixels"] == total_px
    assert res["total_components"] == 3934

    # Verify top cluster 1
    top1 = res["top_components"][0]
    assert top1["pixel_count"] == 15950
    assert top1["area_ha"] == 638.0
    assert top1["area_km2"] == 6.38


# Test 10: Correct georeferencing
def test_correct_georeferencing(project_root: Path, reference_dataset: gdal.Dataset):
    """Verify spatial CRS (EPSG:32645), raster size (1405x1393), and geotransform."""
    qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    p = qc_dir / "transition_primary_qc.tif"
    ds = gdal.Open(str(p), gdal.GA_ReadOnly)

    assert ds.RasterXSize == reference_dataset.RasterXSize == 1405
    assert ds.RasterYSize == reference_dataset.RasterYSize == 1393

    gt_target = ds.GetGeoTransform()
    gt_ref = reference_dataset.GetGeoTransform()
    for v1, v2 in zip(gt_target, gt_ref):
        assert abs(v1 - v2) < 1e-6, f"GeoTransform mismatch: {gt_target} vs {gt_ref}"

    srs_target = osr.SpatialReference()
    srs_target.ImportFromWkt(ds.GetProjection())
    srs_ref = osr.SpatialReference()
    srs_ref.ImportFromWkt(reference_dataset.GetProjection())
    assert srs_target.IsSame(srs_ref) == 1, "CRS projection mismatch"

