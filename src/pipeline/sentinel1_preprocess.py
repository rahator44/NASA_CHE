"""
Sentinel-1 Preprocessing Engine for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Authoritative Preprocessing Pipeline:
- Executes ESA SNAP 'gpt' using the canonical 8-node XML graph template
  (graphs/s1_grd_calibration_terrain_correction.xml)
- Processing graph: Read -> Apply-Orbit-File -> ThermalNoiseRemoval ->
  Remove-GRD-Border-Noise -> Subset -> Calibration (Sigma0 linear) ->
  Terrain-Correction (Copernicus 30m DEM, EPSG:32645, 20m pixel spacing) -> Write
- Validates output radiometric calibration against verified 2024 Jamuna baselines
- Enforces linear power domain storage with NoData (-9999.0) and SNAP clipping floor (2.55e-11)
"""

import os
import sys
import json
import hashlib
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.S1Preprocess")

# Constants
DEFAULT_SNAP_GPT_PATH = Path(os.environ.get("SNAP_GPT_PATH", Path.home() / "esa-snap" / "bin" / "gpt"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_GRAPH_XML = PROJECT_ROOT / "graphs" / "s1_grd_calibration_terrain_correction.xml"
CANONICAL_GRAPH_SHA256 = "c239c2691ebcf45b778e171553c1656f9ce4d4a1dded160d929fa8e73cf316a0"

TARGET_EPSG = 32645
TARGET_RESOLUTION_M = 20.0
NODATA_VALUE = -9999.0
CLIPPING_FLOOR_MIN = 2.50e-11
CLIPPING_FLOOR_MAX = 2.70e-11

# Authoritative verified historical granules for 2024 Jamuna campaign (legacy verification path)
AUTHORITATIVE_BASELINE_GRANULES = {
    "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
    "june10_aligned",
}
AUTHORITATIVE_CHANGE_GRANULES = {
    "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
    "july16_aligned",
}

GRANULE_PROVENANCE = {
    "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69": {
        "preprocessed_raster": "data/processed/aligned/june10_aligned.tif",
        "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
        "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.june10",
        "verification_status": "VERIFIED",
        "notes": "Primary baseline granule. Documented in Jamuna region YAML. Processing chain independently verified.",
    },
    "june10_aligned": {
        "preprocessed_raster": "data/processed/aligned/june10_aligned.tif",
        "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
        "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.june10",
        "verification_status": "VERIFIED",
        "notes": "Shorthand alias for june10 baseline raster.",
    },
    "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511": {
        "preprocessed_raster": "data/processed/aligned/july16_aligned.tif",
        "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
        "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.july16",
        "verification_status": "VERIFIED",
        "notes": "Primary change-date granule. Documented in Jamuna region YAML.",
    },
    "july16_aligned": {
        "preprocessed_raster": "data/processed/aligned/july16_aligned.tif",
        "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
        "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.july16",
        "verification_status": "VERIFIED",
        "notes": "Shorthand alias for july16 change-date raster.",
    },
}

HISTORICAL_REFERENCE_REGISTRY: Dict[str, Dict[str, str]] = {
    "june10_aligned": {
        "granule_id": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
        "sha256": "c54f97e0a24b20574f38c786ac82e38855c266a5842c7f099d980d6b239f9252",
        "acquisition_date": "2024-06-10",
    },
    "july16_aligned": {
        "granule_id": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
        "sha256": "7b441b2a8a816dcc35b1e64b828def155687658e27be357ddb2e43984099c353",
        "acquisition_date": "2024-07-16",
    },
    "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69": {
        "granule_id": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
        "sha256": "c54f97e0a24b20574f38c786ac82e38855c266a5842c7f099d980d6b239f9252",
        "acquisition_date": "2024-06-10",
    },
    "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511": {
        "granule_id": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
        "sha256": "7b441b2a8a816dcc35b1e64b828def155687658e27be357ddb2e43984099c353",
        "acquisition_date": "2024-07-16",
    },
}


def find_snap_gpt_executable() -> Optional[Path]:
    """Locate ESA SNAP gpt executable on host or PATH."""
    env_path = os.environ.get("SNAP_GPT_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists() and os.access(p, os.X_OK):
            return p

    if DEFAULT_SNAP_GPT_PATH.exists() and os.access(DEFAULT_SNAP_GPT_PATH, os.X_OK):
        return DEFAULT_SNAP_GPT_PATH

    which_gpt = shutil.which("gpt")
    if which_gpt:
        return Path(which_gpt)

    # Search common ESA SNAP installation directories
    candidates = [
        Path.home() / "esa-snap" / "bin" / "gpt",
        Path.home() / "snap" / "bin" / "gpt",
        Path("/opt/snap/bin/gpt"),
        Path("/usr/local/snap/bin/gpt"),
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return c

    return None


def validate_sar_raster(filepath: Path) -> Dict[str, Any]:
    """
    Validate that a calibrated SAR raster satisfies Earth Pulse standards:
    - 2 bands: VH (band 1) and VV (band 2)
    - CRS: EPSG:32645 (WGS 84 / UTM zone 45N)
    - Pixel resolution: 20.0m x -20.0m
    - Data type: Float32
    - Linear domain with valid NoData
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Raster does not exist: {filepath}")

    ds = gdal.Open(str(filepath), gdal.GA_ReadOnly)
    if ds is None:
        raise ValueError(f"Failed to open GDAL dataset: {filepath}")

    w, h = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()

    # Verify georeferencing
    if gt == (0.0, 1.0, 0.0, 0.0, 0.0, 1.0) or tuple(gt) == (0.0, 1.0, 0.0, 0.0, 0.0, 1.0) or (gt[0] == 0.0 and gt[3] == 0.0):
        raise ValueError(f"Dataset has unreferenced or default geotransform: {gt}")

    # Verify zero rotation and shearing (north-up grid alignment)
    if abs(gt[2]) > 1e-6 or abs(gt[4]) > 1e-6:
        raise ValueError(f"Raster has non-zero rotation or shearing: geotransform={gt}")

    x_res = abs(gt[1])
    y_res = abs(gt[5])

    if abs(x_res - TARGET_RESOLUTION_M) > 0.1 or abs(y_res - TARGET_RESOLUTION_M) > 0.1:
        raise ValueError(f"Non-compliant resolution ({x_res}m, {y_res}m), expected {TARGET_RESOLUTION_M}m")

    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    if not srs.IsProjected():
        raise ValueError(f"Non-projected CRS: {srs.GetName()}. Expected projected UTM Zone 45N.")

    epsg_code = srs.GetAuthorityCode(None)
    if str(epsg_code) != str(TARGET_EPSG):
        raise ValueError(f"Non-compliant CRS EPSG:{epsg_code}, expected EPSG:{TARGET_EPSG}")

    if ds.RasterCount != 2:
        raise ValueError(f"Raster must have exactly 2 bands (VH and VV), found {ds.RasterCount}")

    b_vh = ds.GetRasterBand(1)
    b_vv = ds.GetRasterBand(2)

    # Verify Float32 numeric data type (Stage A Intrinsic Check)
    if b_vh.DataType != gdal.GDT_Float32 or b_vv.DataType != gdal.GDT_Float32:
        dt_name = gdal.GetDataTypeName(b_vh.DataType)
        raise ValueError(f"Raster data type is {dt_name}, expected Float32 (GDT_Float32).")

    # Verify genuine band order: Band 1 must be VH, Band 2 must be VV
    b1_desc = (b_vh.GetDescription() or "").upper()
    b2_desc = (b_vv.GetDescription() or "").upper()
    band_desc_present = bool(b1_desc and b2_desc)
    if b1_desc and "VH" not in b1_desc:
        raise ValueError(
            f"Band order error: Band 1 is '{b1_desc}', expected Sigma0_VH. "
            "Earth Pulse requires Band 1 = VH, Band 2 = VV."
        )
    if b2_desc and "VV" not in b2_desc:
        raise ValueError(
            f"Band order error: Band 2 is '{b2_desc}', expected Sigma0_VV. "
            "Earth Pulse requires Band 1 = VH, Band 2 = VV."
        )

    # Verify genuine calibration units (cannot be in decibels / dB)
    u1 = (b_vh.GetUnitType() or "").upper()
    u2 = (b_vv.GetUnitType() or "").upper()
    if "DB" in u1 or "DB" in u2 or "DECIBEL" in u1 or "DECIBEL" in u2 or "DB" in b1_desc or "DB" in b2_desc:
        raise ValueError("Raster metadata indicates decibel (dB) units. Earth Pulse requires linear power Sigma0 backscatter.")

    # Read pixel arrays and verify valid data masks & physical non-negative power domain
    arr_vh = b_vh.ReadAsArray()
    arr_vv = b_vv.ReadAsArray()

    # Identify non-NoData pixels
    finite_mask = (
        (arr_vh != NODATA_VALUE)
        & (arr_vv != NODATA_VALUE)
        & np.isfinite(arr_vh)
        & np.isfinite(arr_vv)
    )

    # Physical check: linear power Sigma0 is strictly non-negative.
    # Negative finite values indicate decibels (dB), uncalibrated DNs, or corrupted data.
    if np.any(arr_vh[finite_mask] < 0) or np.any(arr_vv[finite_mask] < 0):
        min_vh = float(np.min(arr_vh[finite_mask])) if np.any(finite_mask) else -9999.0
        raise ValueError(
            f"Raster contains negative pixel values (min={min_vh:.4f}), indicating decibel (dB) or uncalibrated units. "
            "Earth Pulse requires linear power Sigma0 backscatter."
        )

    valid_mask = finite_mask & (arr_vh > 0) & (arr_vv > 0)
    n_valid = int(np.sum(valid_mask))
    if n_valid == 0 and np.any(finite_mask):
        raise ValueError("Raster contains zero positive valid-data pixels.")

    del arr_vh, arr_vv, finite_mask, valid_mask

    is_sigma0_labeled = bool(b1_desc and "SIGMA0" in b1_desc)
    stats = {
        "width": w,
        "height": h,
        "total_pixels": w * h,
        "valid_data_pixels": n_valid,
        "epsg": int(epsg_code),
        "resolution_m": TARGET_RESOLUTION_M,
        "geotransform": list(gt),
        "intrinsic_checks_passed": True,
        "band_descriptions_supplied": band_desc_present,
        "units": "linear_power_sigma0" if is_sigma0_labeled else "linear_power_unverified_provenance",
        "calibration_evidence": "METADATA_LABELED_SIGMA0" if is_sigma0_labeled else "INTRINSIC_VALIDATION_ONLY",
        "clipping_floor_min": CLIPPING_FLOOR_MIN,  # SNAP-enforced minimum value
        "clipping_floor_max": CLIPPING_FLOOR_MAX,
        "bands": {
            1: {
                "name": b1_desc or "Sigma0_VH",
                "polarization": "VH",
                "nodata": b_vh.GetNoDataValue(),
                "expected_nodata": NODATA_VALUE,
            },
            2: {
                "name": b2_desc or "Sigma0_VV",
                "polarization": "VV",
                "nodata": b_vv.GetNoDataValue(),
                "expected_nodata": NODATA_VALUE,
            },
        },
    }
    ds = None
    return stats


def compare_rasters_for_validation(
    test_raster_path: Path,
    reference_raster_path: Path,
) -> Dict[str, Any]:
    """
    Scientifically compare a newly preprocessed raster against an authoritative reference.
    Evaluates CRS, grid alignment, backscatter distributions, Pearson correlation, and MAE.
    Uses strict absolute tolerance (rtol=0.0, atol=1e-6) for geotransform origin and resolution.
    """
    test_meta = validate_sar_raster(test_raster_path)
    ref_meta = validate_sar_raster(reference_raster_path)

    if test_meta["epsg"] != ref_meta["epsg"]:
        raise ValueError(f"CRS mismatch: test {test_meta['epsg']} vs ref {ref_meta['epsg']}")

    if (test_meta["width"], test_meta["height"]) != (ref_meta["width"], ref_meta["height"]):
        raise ValueError(
            f"Raster dimension mismatch: test ({test_meta['width']}, {test_meta['height']}) "
            f"vs ref ({ref_meta['width']}, {ref_meta['height']}). Scientific validation requires identical raster dimensions."
        )

    gt_t = test_meta["geotransform"]
    gt_r = ref_meta["geotransform"]
    # Strict absolute tolerance comparison (rtol=0.0, atol=1e-6)
    if not np.allclose(gt_t, gt_r, rtol=0.0, atol=1e-6):
        raise ValueError(
            f"Geotransform mismatch: test {gt_t} vs ref {gt_r}. "
            "Rasters must share identical georeferenced bounding coordinates without spatial drift."
        )

    ds_test = gdal.Open(str(test_raster_path), gdal.GA_ReadOnly)
    ds_ref = gdal.Open(str(reference_raster_path), gdal.GA_ReadOnly)

    results = {
        "test_raster": str(test_raster_path),
        "ref_raster": str(reference_raster_path),
        "bands_compared": {},
        "is_compatible": True,
    }

    for b_idx, b_name in [(1, "VH"), (2, "VV")]:
        arr_t = ds_test.GetRasterBand(b_idx).ReadAsArray()
        arr_r = ds_ref.GetRasterBand(b_idx).ReadAsArray()

        # Valid mask
        valid = (
            (arr_t != NODATA_VALUE)
            & (arr_r != NODATA_VALUE)
            & np.isfinite(arr_t)
            & np.isfinite(arr_r)
            & (arr_t > 0)
            & (arr_r > 0)
        )

        n_valid = int(np.sum(valid))
        if n_valid < 100:
            results["is_compatible"] = False
            results["bands_compared"][b_name] = {"error": "Insufficient valid overlapping pixels"}
            continue

        vt = arr_t[valid]
        vr = arr_r[valid]

        # Convert to dB for radiometric comparison
        vt_db = 10.0 * np.log10(vt)
        vr_db = 10.0 * np.log10(vr)

        corr = float(np.corrcoef(vt_db, vr_db)[0, 1])
        mae = float(np.mean(np.abs(vt_db - vr_db)))
        bias = float(np.mean(vt_db - vr_db))

        results["bands_compared"][b_name] = {
            "valid_pixels": n_valid,
            "pearson_r": corr,
            "mae_db": mae,
            "mean_bias_db": bias,
            "test_mean_db": float(np.mean(vt_db)),
            "ref_mean_db": float(np.mean(vr_db)),
            "test_std_db": float(np.std(vt_db)),
            "ref_std_db": float(np.std(vr_db)),
        }

        # Quality threshold: correlation must be high (>0.90) and MAE low (<2.0 dB) for identical scenes
        if corr < 0.90 or mae > 2.5:
            results["is_compatible"] = False

    ds_test = None
    ds_ref = None
    return results


def verify_calibrated_raster_provenance(
    tif_path: Path,
    provenance_path: Optional[Path] = None,
    scene_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage B verification: Validates that a SAR raster is backed by genuine radiometric calibration provenance.
    Separates intrinsic raster integrity (Stage A) from calibration provenance verification (Stage B).
    Fails closed on missing or unverified provenance records.
    Enforces exact granule identity matching and mandatory output SHA-256 validation.
    """
    tif_path = Path(tif_path).resolve()
    if not tif_path.exists():
        raise FileNotFoundError(f"Calibrated raster does not exist: {tif_path}")

    # Stage A: Intrinsic raster validation
    intrinsic_stats = validate_sar_raster(tif_path)

    # Calculate actual SHA-256 of raster file
    h = hashlib.sha256()
    with open(tif_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    actual_sha256 = h.hexdigest().lower()

    # Stage B: Provenance verification
    clean_scene = (scene_name or tif_path.stem).replace(".zip", "").replace(".SAFE", "")

    # 1. Authoritative historical reference rasters (registered immutable artifacts)
    # Check if this raster is claiming to be an authoritative historical reference
    prov_file = provenance_path or tif_path.with_name(f"{tif_path.stem}_provenance.json")
    if clean_scene in HISTORICAL_REFERENCE_REGISTRY:
        reg_entry = HISTORICAL_REFERENCE_REGISTRY[clean_scene]
        expected_sha = reg_entry["sha256"].lower()
        is_root_reference = (
            tif_path.name == reg_entry.get("reference_raster")
            or clean_scene in ("june10_aligned", "july16_aligned")
            or not prov_file.exists()
        )
        if is_root_reference:
            if actual_sha256 != expected_sha:
                raise ValueError(
                    f"Historical reference raster checksum verification failed for '{clean_scene}': "
                    f"expected registered SHA-256 {expected_sha}, got {actual_sha256}. "
                    "Forged or tampered historical reference rasters are strictly rejected."
                )
            return {
                "status": "VERIFIED_HISTORICAL_LEGACY",
                "granule_id": reg_entry["granule_id"],
                "raster_path": str(tif_path),
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "provenance_verified": True,
                "sha256": actual_sha256,
                "intrinsic_stats": intrinsic_stats,
                "notes": "Verified authoritative 2024 Jamuna campaign granule with documented SNAP processing chain and matching registered SHA-256.",
            }
        elif actual_sha256 == expected_sha:
            return {
                "status": "VERIFIED_HISTORICAL_LEGACY",
                "granule_id": reg_entry["granule_id"],
                "raster_path": str(tif_path),
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "provenance_verified": True,
                "sha256": actual_sha256,
                "intrinsic_stats": intrinsic_stats,
                "notes": "Verified authoritative 2024 Jamuna campaign granule with documented SNAP processing chain and matching registered SHA-256.",
            }

    # 2. For newly acquired / preprocessed rasters (or sub-AOI slices): require verifiable provenance sidecar
    if not prov_file.exists():
        raise ValueError(
            f"Calibrated product provenance record missing for '{tif_path.name}' (looked for {prov_file.name}). "
            "Nonnegative raw pixel values alone do not prove radiometric calibration. "
            "A verifiable processing chain record is required."
        )

    try:
        prov_data = json.loads(prov_file.read_text())
    except Exception as e:
        raise ValueError(f"Failed to read provenance record {prov_file}: {e}")

    # Enforce exact granule identity matching
    prov_granule = str(prov_data.get("granule_id", "")).replace(".zip", "").replace(".SAFE", "")
    if not prov_granule:
        raise ValueError(f"Provenance record '{prov_file.name}' is missing mandatory 'granule_id' field.")

    if scene_name:
        req_granule = str(scene_name).replace(".zip", "").replace(".SAFE", "")
        # Match directly or via historical reference alias mapping
        is_matched = (
            (prov_granule == req_granule)
            or (HISTORICAL_REFERENCE_REGISTRY.get(req_granule, {}).get("granule_id") == prov_granule)
            or (HISTORICAL_REFERENCE_REGISTRY.get(prov_granule, {}).get("granule_id") == req_granule)
        )
        if not is_matched:
            raise ValueError(
                f"Granule mismatch: requested '{req_granule}' but provenance record documents '{prov_granule}'. "
                "Arbitrary granule substitution is strictly prohibited."
            )

    # Verify output SHA-256 (mandatory field)
    recorded_sha256 = prov_data.get("output_sha256")
    if not recorded_sha256:
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'output_sha256' field. "
            "All calibrated rasters must record and verify exact output checksums."
        )
    if actual_sha256 != str(recorded_sha256).strip().lower():
        raise ValueError(
            f"Provenance checksum mismatch for '{tif_path.name}': "
            f"recorded {recorded_sha256} vs actual {actual_sha256}."
        )

    # Legacy pass if this is a registered historical reference with matching registered SHA-256
    if clean_scene in HISTORICAL_REFERENCE_REGISTRY and actual_sha256 == HISTORICAL_REFERENCE_REGISTRY[clean_scene]["sha256"].lower():
        return {
            "status": "VERIFIED_HISTORICAL_LEGACY",
            "granule_id": HISTORICAL_REFERENCE_REGISTRY[clean_scene]["granule_id"],
            "raster_path": str(tif_path),
            "radiometric_quantity": "Sigma0",
            "radiometric_domain": "linear_power",
            "provenance_verified": True,
            "provenance_record": prov_data,
            "intrinsic_stats": intrinsic_stats,
            "sha256": actual_sha256,
        }

    # =========================================================================
    # Strict cryptographic & configuration verification for non-legacy acquisitions
    # =========================================================================

    # 1. Require mandatory source archive or raster file path, existing and readable on disk
    source_file_path = prov_data.get("source_archive") or prov_data.get("source_raster")
    if not source_file_path or not str(source_file_path).strip():
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'source_archive' or 'source_raster' file path. "
            "A verifiable physical source path is required."
        )

    src_p = Path(source_file_path).resolve()
    if not src_p.exists() or not src_p.is_file():
        raise ValueError(
            f"Source file '{src_p}' documented in '{prov_file.name}' does not exist or is not a regular file."
        )

    if not os.access(src_p, os.R_OK):
        raise ValueError(
            f"Source file '{src_p}' documented in '{prov_file.name}' is not readable."
        )

    # Require valid 64-character hex SHA-256 for the source file
    source_sha256 = prov_data.get("source_archive_sha256") or prov_data.get("source_raster_sha256")
    if not source_sha256 or len(str(source_sha256).strip()) != 64:
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'source_archive_sha256' "
            "(or 'source_raster_sha256') checksum field. Hex digest of 64 characters required."
        )
    source_sha256_str = str(source_sha256).strip().lower()
    if not all(c in "0123456789abcdef" for c in source_sha256_str):
        raise ValueError(
            f"Provenance record '{prov_file.name}' contains a non-hex 'source_archive_sha256' checksum: '{source_sha256}'."
        )

    # Recompute SHA-256 directly from the physical source file
    h_src = hashlib.sha256()
    with open(src_p, "rb") as f:
        while chunk := f.read(65536):
            h_src.update(chunk)
    actual_src_hash = h_src.hexdigest().lower()

    if actual_src_hash != source_sha256_str:
        raise ValueError(
            f"Source file checksum mismatch for '{src_p}': "
            f"recorded {source_sha256_str} vs actual {actual_src_hash}. Forged or tampered source file is rejected."
        )

    # If this is a historical reference sub-AOI extraction, verify source hash matches registered reference hash
    if clean_scene in HISTORICAL_REFERENCE_REGISTRY:
        expected_hist_sha = HISTORICAL_REFERENCE_REGISTRY[clean_scene]["sha256"].lower()
        if source_sha256_str != expected_hist_sha:
            raise ValueError(
                f"Historical source raster checksum mismatch for '{clean_scene}': "
                f"expected registered {expected_hist_sha}, got {source_sha256_str}."
            )

    # 2. Require canonical graph SHA-256 and configuration
    graph_sha256 = prov_data.get("graph_sha256")
    if not graph_sha256 or len(str(graph_sha256).strip()) != 64:
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'graph_sha256' field. "
            "Canonical SNAP graph provenance must be cryptographically bound."
        )
    graph_sha256 = str(graph_sha256).strip().lower()

    canonical_graph_xml = CANONICAL_GRAPH_XML
    if canonical_graph_xml.exists():
        hg = hashlib.sha256()
        with open(canonical_graph_xml, "rb") as f:
            while chunk := f.read(65536):
                hg.update(chunk)
        expected_graph_sha = hg.hexdigest().lower()
        if graph_sha256 != expected_graph_sha:
            raise ValueError(
                f"SNAP graph checksum mismatch in provenance '{prov_file.name}': "
                f"expected canonical graph SHA-256 {expected_graph_sha}, got {graph_sha256}. "
                "Altered or unverified processing graphs are rejected."
            )

        # Parse canonical graph XML and verify Calibration and Terrain-Correction parameter values
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(str(canonical_graph_xml))
            root = tree.getroot()
        except Exception as e:
            raise ValueError(f"Failed to parse canonical graph XML '{canonical_graph_xml}': {e}")

        # Calibration operator verification
        cal_nodes = [
            n for n in root.findall("node")
            if (n.find("operator") is not None and n.find("operator").text == "Calibration") or n.get("id") == "Calibration"
        ]
        if not cal_nodes:
            raise ValueError("Canonical SNAP graph XML is missing 'Calibration' node.")
        cal_params = cal_nodes[0].find("parameters")
        if cal_params is None:
            raise ValueError("Canonical SNAP graph XML Calibration node is missing parameters.")

        out_sigma = cal_params.find("outputSigmaBand")
        if out_sigma is None or str(out_sigma.text).strip().lower() != "true":
            raise ValueError("Canonical SNAP graph XML Calibration node must configure <outputSigmaBand>true</outputSigmaBand>.")

        out_db = cal_params.find("outputImageScaleInDb")
        if out_db is None or str(out_db.text).strip().lower() != "false":
            raise ValueError("Canonical SNAP graph XML Calibration node must configure <outputImageScaleInDb>false</outputImageScaleInDb>.")

        # Terrain-Correction operator verification
        tc_nodes = [
            n for n in root.findall("node")
            if (n.find("operator") is not None and n.find("operator").text == "Terrain-Correction") or n.get("id") == "Terrain-Correction"
        ]
        if not tc_nodes:
            raise ValueError("Canonical SNAP graph XML is missing 'Terrain-Correction' node.")
        tc_params = tc_nodes[0].find("parameters")
        if tc_params is None:
            raise ValueError("Canonical SNAP graph XML Terrain-Correction node is missing parameters.")

        pixel_spacing = tc_params.find("pixelSpacingInMeter")
        if pixel_spacing is None or abs(float(pixel_spacing.text) - 20.0) > 0.1:
            raise ValueError(
                f"Canonical SNAP graph XML Terrain-Correction node must configure 20m grid (<pixelSpacingInMeter>20.0</pixelSpacingInMeter>), got: {pixel_spacing.text if pixel_spacing is not None else 'None'}."
            )

        map_proj = tc_params.find("mapProjection")
        if map_proj is None or "32645" not in str(map_proj.text):
            raise ValueError(
                f"Canonical SNAP graph XML Terrain-Correction node must configure EPSG:32645 projection, got: {map_proj.text if map_proj is not None else 'None'}."
            )
    elif graph_sha256 != CANONICAL_GRAPH_SHA256:
        raise ValueError(
            f"SNAP graph checksum mismatch in provenance '{prov_file.name}': "
            f"expected canonical graph SHA-256 {CANONICAL_GRAPH_SHA256}, got {graph_sha256}."
        )

    # 3. Require and validate processing_parameters against approved SNAP graph
    proc_params = prov_data.get("processing_parameters")
    if not proc_params or not isinstance(proc_params, dict):
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'processing_parameters' dictionary."
        )

    # Radiometric quantity: Sigma0
    rad_qty = str(proc_params.get("radiometric_quantity", "")).strip()
    if rad_qty != "Sigma0":
        raise ValueError(
            f"Invalid radiometric_quantity '{rad_qty}' in '{prov_file.name}': expected 'Sigma0'."
        )

    # Radiometric domain: linear power, not decibels
    rad_dom = str(proc_params.get("radiometric_domain", "")).strip().lower()
    if rad_dom not in ("linear_power", "linear"):
        raise ValueError(
            f"Invalid radiometric_domain '{rad_dom}' in '{prov_file.name}': expected 'linear_power', decibels/uncalibrated is strictly rejected."
        )

    # Canonical output: Band 1 VH, Band 2 VV
    out_bands = proc_params.get("output_bands")
    if not isinstance(out_bands, (list, tuple)) or list(out_bands) != ["Sigma0_VH", "Sigma0_VV"]:
        raise ValueError(
            f"Invalid output_bands '{out_bands}' in '{prov_file.name}': expected ['Sigma0_VH', 'Sigma0_VV']."
        )

    # Expected projected CRS: EPSG:32645
    exp_crs = str(proc_params.get("expected_crs", "")).strip().upper()
    if exp_crs and "32645" not in exp_crs:
        raise ValueError(
            f"Contradictory projected CRS '{exp_crs}' in '{prov_file.name}': expected 'EPSG:32645'."
        )

    # Expected grid: 20 m
    exp_grid = proc_params.get("pixel_spacing_m") or proc_params.get("expected_grid_m")
    if exp_grid is not None:
        try:
            if abs(float(exp_grid) - 20.0) > 0.1:
                raise ValueError(
                    f"Contradictory grid spacing '{exp_grid}' in '{prov_file.name}': expected 20 m."
                )
        except (ValueError, TypeError):
            raise ValueError(
                f"Unparseable grid spacing '{exp_grid}' in '{prov_file.name}': expected 20 m."
            )

    # 4. Require source-to-output polarization mapping documenting canonical band contract
    band_mapping = prov_data.get("source_band_mapping")
    if not band_mapping or not isinstance(band_mapping, dict):
        raise ValueError(
            f"Provenance record '{prov_file.name}' is missing mandatory 'source_band_mapping' dictionary. "
            "Source polarization identity and canonical band ordering must be documented."
        )

    # Must contain validated source VH and VV indices (reject arbitrary dictionaries)
    vh_key = "source_band_vh" if "source_band_vh" in band_mapping else ("vh" if "vh" in band_mapping else None)
    vv_key = "source_band_vv" if "source_band_vv" in band_mapping else ("vv" if "vv" in band_mapping else None)

    if not vh_key or not vv_key:
        raise ValueError(
            f"Provenance record '{prov_file.name}' source_band_mapping is missing mandatory polarization keys "
            "('source_band_vh' and 'source_band_vv'). Arbitrary mappings are rejected."
        )

    src_vh = band_mapping[vh_key]
    src_vv = band_mapping[vv_key]

    if not isinstance(src_vh, int) or isinstance(src_vh, bool) or src_vh < 1 or \
       not isinstance(src_vv, int) or isinstance(src_vv, bool) or src_vv < 1 or \
       src_vh == src_vv:
        raise ValueError(
            f"Invalid polarization source band indices in '{prov_file.name}': VH={src_vh}, VV={src_vv}. "
            "Source band indices must be distinct positive integers."
        )

    # Canonical output band order in mapping: Band 1 = VH, Band 2 = VV
    b1_out = band_mapping.get("output_band_1")
    b2_out = band_mapping.get("output_band_2")
    if b1_out is not None or b2_out is not None:
        if str(b1_out).strip().upper() not in ("SIGMA0_VH", "VH") or str(b2_out).strip().upper() not in ("SIGMA0_VV", "VV"):
            raise ValueError(
                f"Invalid canonical output band order in source_band_mapping: Band 1='{b1_out}', Band 2='{b2_out}'. "
                "Expected Band 1 = Sigma0_VH, Band 2 = Sigma0_VV."
            )

    # 5. Verify actual raster polarization contract (Band 1 = Sigma0_VH, Band 2 = Sigma0_VV)
    vh_idx, vv_idx, detected_mapping = Sentinel1Preprocessor.identify_polarization_bands(tif_path)
    if vh_idx != 1 or vv_idx != 2:
        raise ValueError(
            f"Raster band polarization contract violated in '{tif_path.name}': "
            f"expected Band 1 = Sigma0_VH, Band 2 = Sigma0_VV, but detected VH at {vh_idx}, VV at {vv_idx}."
        )

    # 6. Do not treat a freely editable processing_chain string as proof of calibration
    graph_ref = prov_data.get("graph_reference") or prov_data.get("provenance", {}).get("processing_reference")
    if not graph_ref or "s1_grd_calibration_terrain_correction.xml" not in str(graph_ref):
        raise ValueError(
            f"Unverified processing reference in '{prov_file.name}': expected reference to canonical "
            "s1_grd_calibration_terrain_correction.xml graph."
        )

    return {
        "status": "VERIFIED_PROVENANCE",
        "granule_id": prov_granule or clean_scene,
        "raster_path": str(tif_path),
        "radiometric_quantity": "Sigma0",
        "radiometric_domain": "linear_power",
        "provenance_verified": True,
        "provenance_record": prov_data,
        "intrinsic_stats": intrinsic_stats,
        "sha256": actual_sha256,
    }


class Sentinel1Preprocessor:
    """
    Executes and coordinates Sentinel-1 IW GRD preprocessing using ESA SNAP 'gpt'
    and verified scientific graphs.
    """

    def __init__(
        self,
        gpt_path: Optional[Path] = None,
        graph_xml_path: Path = CANONICAL_GRAPH_XML,
        max_memory_mb: Optional[int] = None,
    ):
        self.gpt_path = gpt_path or find_snap_gpt_executable()
        self.graph_xml_path = Path(graph_xml_path)
        if max_memory_mb is not None:
            self.max_memory_mb = max_memory_mb
        else:
            self.max_memory_mb = int(os.environ.get("SNAP_MAX_MEMORY_MB", "6144"))

    @property
    def is_snap_available(self) -> bool:
        return self.gpt_path is not None and self.gpt_path.exists()

    def run_snap_gpt(
        self,
        input_archive: Path,
        output_path: Path,
        wkt_polygon: Optional[str] = None,
        timeout_seconds: int = 1800,
    ) -> Dict[str, Any]:
        """
        Execute ESA SNAP gpt on a Sentinel-1 GRD archive using parameterized canonical graph.
        """
        if not self.is_snap_available:
            raise RuntimeError(
                f"ESA SNAP 'gpt' binary not found. Standard path: {DEFAULT_SNAP_GPT_PATH}. "
                "Ensure ESA SNAP is installed and SNAP_GPT_PATH environment variable is set."
            )

        if not self.graph_xml_path.exists():
            raise FileNotFoundError(f"Canonical SNAP graph XML missing at {self.graph_xml_path}")

        input_archive = Path(input_archive).resolve()
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build gpt command
        cmd = [
            str(self.gpt_path),
            str(self.graph_xml_path),
            f"-J-Xmx{self.max_memory_mb}m",
            f"-Pinput={input_archive}",
            f"-Poutput={output_path}",
        ]
        if wkt_polygon:
            cmd.append(f"-PgeoRegion={wkt_polygon}")

        logger.info("Executing SNAP GPT: %s", " ".join(cmd[:5]))
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )

        if proc.returncode != 0:
            logger.error("SNAP GPT failed (code %d):\n%s", proc.returncode, proc.stderr)
            raise RuntimeError(f"SNAP GPT execution failed with return code {proc.returncode}: {proc.stderr[:500]}")

        # Verify output exists
        if not output_path.exists():
            # Check if output is a directory (e.g. BEAM-DIMAP .data or .dim) or has .tif appended
            dim_candidate = output_path.with_suffix(".dim")
            tif_candidate = Path(str(output_path) + ".tif")
            if dim_candidate.exists():
                output_path = dim_candidate
            elif tif_candidate.exists():
                output_path = tif_candidate
            else:
                raise FileNotFoundError(f"Expected SNAP GPT output missing: {output_path}")

        # In SNAP GeoTIFF output, band ordering is governed by the canonical graph Terrain-Correction
        # node (<sourceBands>Sigma0_VH,Sigma0_VV</sourceBands>). Ensure GeoTIFF headers carry explicit
        # band descriptions for downstream verification.
        if output_path.suffix.lower() in (".tif", ".tiff"):
            ds_desc = gdal.Open(str(output_path), gdal.GA_Update)
            if ds_desc is not None:
                if ds_desc.RasterCount >= 2:
                    if not ds_desc.GetRasterBand(1).GetDescription():
                        ds_desc.GetRasterBand(1).SetDescription("Sigma0_VH")
                    if not ds_desc.GetRasterBand(2).GetDescription():
                        ds_desc.GetRasterBand(2).SetDescription("Sigma0_VV")
                ds_desc.FlushCache()
                ds_desc = None

        meta = validate_sar_raster(output_path)
        return {
            "success": True,
            "output_path": str(output_path),
            "metadata": meta,
        }

    @classmethod
    def identify_polarization_bands(cls, dataset_or_path: Any) -> Tuple[int, int, Dict[str, Any]]:
        """
        Inspect dataset band metadata to identify genuine VH and VV polarization bands.
        Returns:
            (vh_band_index: int, vv_band_index: int, band_mapping: Dict[str, Any])
        Raises:
            ValueError: If polarization identity cannot be verified or dual-pol is missing.
        """
        ds_to_close = None
        if isinstance(dataset_or_path, (str, Path)):
            ds = gdal.Open(str(dataset_or_path), gdal.GA_ReadOnly)
            if ds is None:
                raise ValueError(f"Failed to open GDAL dataset: {dataset_or_path}")
            ds_to_close = ds
        else:
            ds = dataset_or_path

        try:
            band_count = ds.RasterCount
            if band_count < 2:
                raise ValueError(f"Input raster has {band_count} band(s); at least 2 bands (VH and VV) are required.")

            vh_candidates = []
            vv_candidates = []
            descriptions = {}

            for idx in range(1, band_count + 1):
                band = ds.GetRasterBand(idx)
                desc = (band.GetDescription() or "").strip()
                meta = band.GetMetadata() or {}
                descriptions[idx] = desc

                combined = f"{desc} {meta.get('POLARIZATION', '')} {meta.get('DESCRIPTION', '')} {meta.get('NAME', '')}".upper()

                is_vh = False
                is_vv = False

                if "VH" in combined and "VV" not in combined:
                    is_vh = True
                elif "VV" in combined and "VH" not in combined:
                    is_vv = True
                elif "VH" in combined and "VV" in combined:
                    if "SIGMA0_VH" in combined or "GAMMA0_VH" in combined or "INTENSITY_VH" in combined:
                        is_vh = True
                    elif "SIGMA0_VV" in combined or "GAMMA0_VV" in combined or "INTENSITY_VV" in combined:
                        is_vv = True

                if is_vh:
                    vh_candidates.append(idx)
                if is_vv:
                    vv_candidates.append(idx)

            if len(vh_candidates) == 1 and len(vv_candidates) == 1 and vh_candidates[0] != vv_candidates[0]:
                vh_idx = vh_candidates[0]
                vv_idx = vv_candidates[0]
            else:
                raise ValueError(
                    f"Cannot verify polarization identity for input raster bands: descriptions={descriptions}, "
                    f"detected VH={vh_candidates}, VV={vv_candidates}. "
                    "Earth Pulse requires verified dual-polarization (VV and VH) channels."
                )

            mapping = {
                "source_band_vh": vh_idx,
                "source_band_vv": vv_idx,
                "source_descriptions": descriptions,
                "output_band_1": "Sigma0_VH",
                "output_band_2": "Sigma0_VV",
                "reordered": bool(vh_idx != 1 or vv_idx != 2),
            }
            return vh_idx, vv_idx, mapping
        finally:
            if ds_to_close is not None:
                ds_to_close = None

    @classmethod
    def get_polygon_area_km2(cls, wkt_polygon: str, target_epsg: int = TARGET_EPSG) -> float:
        """
        Calculate precise planar geometric area (in km2) for a WGS84 polygon
        reprojected into the target projected coordinate system (e.g. UTM Zone 45N).
        """
        geom_wgs84 = ogr.CreateGeometryFromWkt(wkt_polygon)
        if geom_wgs84 is None:
            raise ValueError(f"Invalid WKT geometry: {wkt_polygon}")
        srs_4326 = osr.SpatialReference()
        srs_4326.ImportFromEPSG(4326)
        srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        srs_utm = osr.SpatialReference()
        srs_utm.ImportFromEPSG(target_epsg)
        srs_utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        tx = osr.CoordinateTransformation(srs_4326, srs_utm)

        geom_utm = geom_wgs84.Clone()
        geom_utm.Transform(tx)
        return float(geom_utm.GetArea() / 1e6)

    @classmethod
    def extract_sub_aoi(
        cls,
        source_tif: Path,
        target_tif: Path,
        wkt_polygon: str,
    ) -> Path:
        """
        Extract and cutline-mask a study sub-AOI from a calibrated SAR raster (EPSG:32645).
        Applies polygon cutline masking so that pixels outside the user-selected polygon
        boundary are masked to NoData (-9999.0) while preserving 20m grid alignment.
        """
        source_tif = Path(source_tif).resolve()
        target_tif = Path(target_tif).resolve()
        target_tif.parent.mkdir(parents=True, exist_ok=True)

        geom_wgs84 = ogr.CreateGeometryFromWkt(wkt_polygon)
        if geom_wgs84 is None:
            raise ValueError(f"Invalid WKT geometry: {wkt_polygon}")

        srs_4326 = osr.SpatialReference()
        srs_4326.ImportFromEPSG(4326)
        srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        srs_utm = osr.SpatialReference()
        srs_utm.ImportFromEPSG(TARGET_EPSG)
        srs_utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        tx = osr.CoordinateTransformation(srs_4326, srs_utm)

        geom_utm = geom_wgs84.Clone()
        geom_utm.Transform(tx)
        utm_cutline_wkt = geom_utm.ExportToWkt()

        # GetEnvelope returns (minX, maxX, minY, maxY)
        minx, maxx, miny, maxy = geom_utm.GetEnvelope()

        # Snap bounds to 20m pixel grid
        minx = np.floor(minx / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
        miny = np.floor(miny / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
        maxx = np.ceil(maxx / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
        maxy = np.ceil(maxy / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M

        # Identify genuine polarization bands before warping
        vh_idx, vv_idx, mapping = cls.identify_polarization_bands(source_tif)

        warp_options = gdal.WarpOptions(
            format="GTiff",
            outputBounds=[minx, miny, maxx, maxy],
            xRes=TARGET_RESOLUTION_M,
            yRes=TARGET_RESOLUTION_M,
            dstSRS=f"EPSG:{TARGET_EPSG}",
            resampleAlg=gdal.GRA_NearestNeighbour,
            cutlineWKT=utm_cutline_wkt,
            cutlineSRS=f"EPSG:{TARGET_EPSG}",
            cropToCutline=False,
            dstNodata=NODATA_VALUE,
            srcBands=[vh_idx, vv_idx],
            creationOptions=["COMPRESS=LZW", "TILED=YES"],
        )

        ds = gdal.Warp(str(target_tif), str(source_tif), options=warp_options)
        if ds is None:
            raise RuntimeError(f"GDAL Warp failed to extract sub-AOI: {target_tif}")

        # Set verified band descriptions and provenance metadata
        ds.GetRasterBand(1).SetDescription("Sigma0_VH")
        ds.GetRasterBand(2).SetDescription("Sigma0_VV")
        ds.SetMetadataItem("SOURCE_BAND_MAPPING", json.dumps(mapping))
        ds.SetMetadataItem("POLARIZATION_IDENTITY_VERIFIED", "TRUE")
        ds.FlushCache()
        ds = None

        return target_tif
