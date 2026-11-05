#!/usr/bin/env python3
"""
Unit tests for Earth Pulse Phase 3B: Multi-Temporal Flood-Change Detection Engine.
Covers 15 required test topics using synthetic arrays and temporary GDAL datasets.
"""

from pathlib import Path
import tempfile
import numpy as np
import pytest
from osgeo import gdal, ogr, osr

# Robust dual-resolution import pattern
try:
    from scripts.detect_flood_change_phase3b import (
        compute_transition_map,
        calculate_transition_statistics,
        analyze_connected_components,
        evaluate_method_sensitivity,
        write_geotiff,
        rasterize_aoi_mask,
        polygonize_layer_to_geojson,
        CLASS_PERSISTENT_WATER,
        CLASS_NEWLY_INUNDATED,
        CLASS_RECEDED_WATER,
        CLASS_PERSISTENT_NON_WATER,
        CLASS_INDETERMINATE,
        CLASS_NODATA_INVALID,
        PRELIMINARY_AOI_WKT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )
except ImportError:
    from detect_flood_change_phase3b import (
        compute_transition_map,
        calculate_transition_statistics,
        analyze_connected_components,
        evaluate_method_sensitivity,
        write_geotiff,
        rasterize_aoi_mask,
        polygonize_layer_to_geojson,
        CLASS_PERSISTENT_WATER,
        CLASS_NEWLY_INUNDATED,
        CLASS_RECEDED_WATER,
        CLASS_PERSISTENT_NON_WATER,
        CLASS_INDETERMINATE,
        CLASS_NODATA_INVALID,
        PRELIMINARY_AOI_WKT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )


def create_synthetic_ref_raster(filepath: Path, width: int = 100, height: int = 100):
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(filepath), width, height, 1, gdal.GDT_Byte)
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32645)
    ds.SetProjection(srs.ExportToWkt())
    b = ds.GetRasterBand(1)
    b.Fill(0)
    ds.FlushCache()
    ds = None


# 1. Persistent water logic (June==1 AND July==1 -> Class 1)
def test_persistent_water_logic():
    june = np.array([[1, 1], [0, 0]], dtype=np.uint8)
    july = np.array([[1, 0], [1, 0]], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    assert trans[0, 0] == CLASS_PERSISTENT_WATER


# 2. Newly inundated candidate logic (June==0 AND July==1 -> Class 2)
def test_newly_inundated_candidate_logic():
    june = np.array([[0]], dtype=np.uint8)
    july = np.array([[1]], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    assert trans[0, 0] == CLASS_NEWLY_INUNDATED


# 3. Receded water logic (June==1 AND July==0 -> Class 3)
def test_receded_water_logic():
    june = np.array([[1]], dtype=np.uint8)
    july = np.array([[0]], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    assert trans[0, 0] == CLASS_RECEDED_WATER


# 4. Persistent non-water logic (June==0 AND July==0 -> Class 4)
def test_persistent_non_water_logic():
    june = np.array([[0]], dtype=np.uint8)
    july = np.array([[0]], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    assert trans[0, 0] == CLASS_PERSISTENT_NON_WATER


# 5. Indeterminate priority (June or July == 2 -> Class 5)
def test_indeterminate_priority():
    june = np.array([2, 1, 0], dtype=np.uint8)
    july = np.array([1, 2, 2], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    assert trans[0] == CLASS_INDETERMINATE
    assert trans[1] == CLASS_INDETERMINATE
    assert trans[2] == CLASS_INDETERMINATE


# 6. NoData priority (June or July == 3 -> Class 6, overrides indeterminate)
def test_nodata_priority():
    june = np.array([3, 2, 0, 1], dtype=np.uint8)
    july = np.array([2, 3, 3, 3], dtype=np.uint8)
    trans = compute_transition_map(june, july)
    # Even when one is 2 (indeterminate), 3 (NoData) takes absolute priority
    assert trans[0] == CLASS_NODATA_INVALID
    assert trans[1] == CLASS_NODATA_INVALID
    assert trans[2] == CLASS_NODATA_INVALID
    assert trans[3] == CLASS_NODATA_INVALID


# 7. Category conservation (Sum of Classes 1..6 == Total cells)
def test_category_conservation():
    np.random.seed(123)
    shape = (50, 50)
    june = np.random.choice([0, 1, 2, 3], size=shape, p=[0.6, 0.2, 0.15, 0.05]).astype(np.uint8)
    july = np.random.choice([0, 1, 2, 3], size=shape, p=[0.5, 0.35, 0.1, 0.05]).astype(np.uint8)

    trans = compute_transition_map(june, july)
    stats = calculate_transition_statistics(trans)

    sum_cells = (
        stats["persistent_water_cells"]
        + stats["newly_inundated_candidate_cells"]
        + stats["receded_water_cells"]
        + stats["persistent_non_water_cells"]
        + stats["indeterminate_cells"]
        + stats["nodata_cells"]
    )
    assert sum_cells == stats["total_cells"] == 2500


# 8. Pixel area conversion (20m x 20m = 400 m² = 0.04 ha = 0.0004 km²)
def test_pixel_area_conversion():
    trans = np.full((10, 10), CLASS_PERSISTENT_NON_WATER, dtype=np.uint8)
    trans[:2, :5] = CLASS_NEWLY_INUNDATED # 10 pixels

    stats = calculate_transition_statistics(trans, pixel_size_m=20.0)
    # 10 pixels * 400 m2 = 4,000 m2 = 0.4 ha = 0.004 km2
    assert abs(stats["newly_inundated_candidate_area_ha"] - 0.4) < 1e-4
    assert abs(stats["newly_inundated_candidate_area_km2"] - 0.004) < 1e-6


# 9. Net water-area reconciliation identity
def test_net_water_area_reconciliation():
    june = np.array([
        [1, 1, 1, 0, 0],
        [1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ], dtype=np.uint8) # 5 water cells

    july = np.array([
        [1, 1, 0, 0, 0],
        [1, 1, 1, 1, 0],
        [0, 0, 1, 1, 0],
    ], dtype=np.uint8) # 8 water cells

    trans = compute_transition_map(june, july)
    stats = calculate_transition_statistics(trans)

    # Class 1 (Persistent): (0,0), (0,1), (1,0), (1,1) -> 4 cells
    # Class 2 (Newly Inundated): (1,2), (1,3), (2,2), (2,3) -> 4 cells
    # Class 3 (Receded): (0,2) -> 1 cell
    # Class 4 (Persistent Non-Water): (0,3), (0,4), (1,4), (2,0), (2,1), (2,4) -> 6 cells
    assert stats["persistent_water_cells"] == 4
    assert stats["newly_inundated_candidate_cells"] == 4
    assert stats["receded_water_cells"] == 1
    assert stats["persistent_non_water_cells"] == 6

    # Identity check:
    # Net Change = Gross Inundation - Gross Recession = 4 - 1 = 3 cells
    # July Water - June Water = 8 - 5 = 3 cells
    assert stats["reconciliation_identity_holds"] is True
    assert stats["valid_july_water_cells"] - stats["valid_june_water_cells"] == 3


# 10. AOI masking
def test_aoi_masking_integration(tmp_path):
    p_ref = tmp_path / "ref.tif"
    create_synthetic_ref_raster(p_ref, width=1405, height=1393)
    aoi_mask = rasterize_aoi_mask(p_ref, PRELIMINARY_AOI_WKT)
    assert aoi_mask.shape == (1393, 1405)
    assert np.sum(aoi_mask) > 100000


# 11. Connected-component calculations
def test_connected_component_calculations():
    # Synthetic grid with 2 separate inundation clusters
    arr = np.zeros((20, 20), dtype=bool)
    arr[2:5, 2:5] = True   # 3x3 = 9 pixels (Cluster 1)
    arr[12:14, 12:15] = True # 2x3 = 6 pixels (Cluster 2)

    gt = (1000.0, 20.0, 0.0, 2000.0, 0.0, -20.0)
    res = analyze_connected_components(arr, gt, top_n=10)

    assert res["total_components"] == 2
    assert res["total_pixels"] == 15
    assert len(res["top_components"]) == 2

    # Cluster 1 should be ranked #1 with 9 pixels
    c1 = res["top_components"][0]
    assert c1["pixel_count"] == 9
    assert abs(c1["area_ha"] - (9 * 0.04)) < 1e-4

    # Cluster 2 should be ranked #2 with 6 pixels
    c2 = res["top_components"][1]
    assert c2["pixel_count"] == 6
    assert abs(c2["area_ha"] - (6 * 0.04)) < 1e-4


# 12. GeoTIFF georeferencing
def test_geotiff_georeferencing(tmp_path):
    p_ref = tmp_path / "ref.tif"
    create_synthetic_ref_raster(p_ref, width=50, height=50)
    ref_ds = gdal.Open(str(p_ref))

    p_out = tmp_path / "out_trans.tif"
    data = np.ones((50, 50), dtype=np.uint8)
    write_geotiff(data, p_out, ref_ds, nodata_value=6, band_description="Test")

    out_ds = gdal.Open(str(p_out))
    assert out_ds.RasterXSize == 50
    assert out_ds.RasterYSize == 50
    assert out_ds.GetProjection() == ref_ds.GetProjection()
    assert out_ds.GetGeoTransform() == ref_ds.GetGeoTransform()
    assert out_ds.GetRasterBand(1).GetNoDataValue() == 6
    assert out_ds.GetRasterBand(1).GetDescription() == "Test"


# 13. Consistent transition class codes
def test_consistent_transition_class_codes():
    june = np.array([[1, 0, 1, 0, 2, 3]], dtype=np.uint8)
    july = np.array([[1, 1, 0, 0, 0, 1]], dtype=np.uint8)
    trans = compute_transition_map(june, july)

    # Must be in [1..6]
    assert np.all((trans >= 1) & (trans <= 6))
    assert list(trans.ravel()) == [1, 2, 3, 4, 5, 6]


# 14. Method sensitivity calculations
def test_method_sensitivity_calculations():
    aoi_mask = np.ones((10, 10), dtype=bool)
    # Primary: 20 newly inundated cells
    prim = np.full((10, 10), CLASS_PERSISTENT_NON_WATER, dtype=np.uint8)
    prim[:4, :5] = CLASS_NEWLY_INUNDATED # 20 cells

    # Secondary: 22 cells (18 overlapping, 4 non-overlapping, 2 missing)
    sec = np.full((10, 10), CLASS_PERSISTENT_NON_WATER, dtype=np.uint8)
    sec[:4, :4] = CLASS_NEWLY_INUNDATED # 16 cells
    sec[4:6, :3] = CLASS_NEWLY_INUNDATED # 6 cells

    res = evaluate_method_sensitivity(prim, sec, aoi_mask, "Test_Sensitivity")
    assert res["jaccard_iou"] > 0.5
    assert res["cohens_kappa"] > 0.5
    assert res["overall_agreement_pct"] > 80.0


# 15. Protection against output overwriting
def test_protection_against_output_overwriting(tmp_path):
    p_ref = tmp_path / "ref.tif"
    create_synthetic_ref_raster(p_ref, width=10, height=10)
    ref_ds = gdal.Open(str(p_ref))

    p_out = tmp_path / "protected.tif"
    data1 = np.ones((10, 10), dtype=np.uint8)
    write_geotiff(data1, p_out, ref_ds, overwrite=True)

    # Modify data and try to write with overwrite=False
    data2 = np.full((10, 10), 2, dtype=np.uint8)
    write_geotiff(data2, p_out, ref_ds, overwrite=False)

    ds_check = gdal.Open(str(p_out))
    arr_check = ds_check.GetRasterBand(1).ReadAsArray()
    # Must still contain data1 (value 1), NOT data2
    assert np.all(arr_check == 1)

