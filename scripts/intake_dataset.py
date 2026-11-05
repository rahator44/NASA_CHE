#!/usr/bin/env python3
"""
Earth Pulse Incoming Dataset Intake & Readiness Validator
Prepares for unexpected multi-sensor, multi-region data drops (e.g., Nov 12-13, 2026).
Implements the 9-step intake verification protocol.
"""

import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import json
import os
import sys

from osgeo import gdal, osr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_sensor_config, load_region_config
from src.core.dataset_manifest import DatasetManifest, DatasetRecord
from src.ml.adapters import SensorAdapterRegistry, IncompatibleSensorError

gdal.UseExceptions()


@dataclass
class IntakeAssessment:
    input_path: str
    file_exists: bool
    file_size_bytes: int
    sha256_checksum: str
    sensor_identified: str
    product_type_identified: str
    acquisition_date: Optional[str]
    geographical_coverage: Dict[str, Any]
    crs_identified: Optional[str]
    spatial_resolution_m: Optional[Tuple[float, float]]
    raster_dimensions: Optional[Tuple[int, int]]
    band_count: int
    feature_compatibility: Dict[str, Any]
    reference_labels_available: bool
    use_case_determination: str
    intake_status: str
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetIntakePipeline:
    """Executes the formal 9-step intake assessment on an incoming satellite dataset."""

    def __init__(self, project_root: Optional[Path] = None):
        self.root = project_root or PROJECT_ROOT
        self.adapter_registry = SensorAdapterRegistry()

    def inspect_dataset(
        self,
        file_path: Path,
        region_hint: Optional[str] = None,
        sensor_hint: Optional[str] = None,
        reference_label_path: Optional[Path] = None,
    ) -> IntakeAssessment:
        recs: List[str] = []

        # Step 1: Inventory & Integrity Check
        if not file_path.exists():
            return IntakeAssessment(
                input_path=str(file_path),
                file_exists=False,
                file_size_bytes=0,
                sha256_checksum="",
                sensor_identified="UNKNOWN",
                product_type_identified="UNKNOWN",
                acquisition_date=None,
                geographical_coverage={},
                crs_identified=None,
                spatial_resolution_m=None,
                raster_dimensions=None,
                band_count=0,
                feature_compatibility={"compatible": False, "reason": "File does not exist"},
                reference_labels_available=False,
                use_case_determination="REJECTED",
                intake_status="FAILED_INTEGRITY",
                recommendations=["Verify path and re-transfer file."],
            )

        file_size = file_path.stat().st_size
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        sha256_val = hasher.hexdigest()

        # Step 2 & 3: Sensor & Product Type Identification
        fn = file_path.name.upper()
        sensor = "UNKNOWN"
        prod_type = "UNKNOWN"
        acq_date = None

        if "S1A_" in fn or "S1B_" in fn:
            sensor = "sentinel1"
            prod_type = "GRD_IW" if "GRDH" in fn or "GRD" in fn else "SLC"
            # Parse acquisition date from standard ESA naming
            parts = fn.split("_")
            for p in parts:
                if len(p) == 15 and p.startswith("202"):
                    acq_date = f"{p[:4]}-{p[4:6]}-{p[6:8]}T{p[9:11]}:{p[11:13]}:{p[13:15]}Z"
                    break
        elif "NISAR" in fn:
            sensor = "nisar"
            prod_type = "L2_GCOV" if "GCOV" in fn else "L1_GSLC"
        elif "ALOS" in fn or "ALPSRP" in fn:
            sensor = "alos_palsar"
            prod_type = "L2_RTC"
        elif "S2A_" in fn or "S2B_" in fn:
            sensor = "sentinel2"
            prod_type = "MSIL2A"
        elif sensor_hint:
            sensor = sensor_hint
            prod_type = "USER_SPECIFIED"

        # Step 4 & 5: Inspect Metadata, CRS, and Resolution
        crs_str = None
        res_m = None
        dims = None
        bands = 0
        geo_cov = {}

        try:
            ds = gdal.Open(str(file_path), gdal.GA_ReadOnly)
            if ds is not None:
                dims = (ds.RasterXSize, ds.RasterYSize)
                bands = ds.RasterCount
                gt = ds.GetGeoTransform()
                if gt:
                    res_m = (abs(float(gt[1])), abs(float(gt[5])))
                proj = ds.GetProjection()
                if proj:
                    srs = osr.SpatialReference(wkt=proj)
                    auth_name = srs.GetAttrValue("AUTHORITY", 0)
                    auth_code = srs.GetAttrValue("AUTHORITY", 1)
                    if auth_name and auth_code:
                        crs_str = f"{auth_name}:{auth_code}"
                    else:
                        crs_str = "PROJ_DEFINED"
                
                # Approximate bounding box in native CRS
                if gt:
                    minx = gt[0]
                    maxy = gt[3]
                    maxx = minx + gt[1] * ds.RasterXSize
                    miny = maxy + gt[5] * ds.RasterYSize
                    geo_cov = {"native_bbox": [minx, miny, maxx, maxy]}
                ds = None
        except Exception as e:
            recs.append(f"GDAL probe warning: Could not open as raster directly ({str(e)}). May be archive or bundle.")

        # Step 6: Feature Compatibility Assessment
        feat_compat = {"compatible": False, "reason": None}
        if sensor == "sentinel1":
            try:
                adapter = self.adapter_registry.get_adapter("sentinel1")
                is_compat, reason = adapter.check_compatibility({
                    "sensor": "sentinel1",
                    "band": "C-band",
                    "polarization": ["VV", "VH"] if bands >= 2 else ["VV"]
                })
                feat_compat = {"compatible": is_compat, "adapter": "Sentinel1GRDAdapter", "reason": reason}
            except Exception as e:
                feat_compat = {"compatible": False, "reason": str(e)}
        else:
            feat_compat = {
                "compatible": False,
                "reason": (
                    f"Sensor '{sensor}' lacks a native adapter. "
                    "Cross-band physics requires dedicated calibration and feature adapter."
                )
            }
            recs.append(f"Create a dedicated adapter for sensor '{sensor}' before training.")

        # Step 7: Reference Label Availability
        ref_avail = False
        if reference_label_path and reference_label_path.exists():
            ref_avail = True
        elif region_hint == "jamuna_sirajganj":
            ref_avail = True  # Verified existing optical SCL reference available

        # Step 8 & 9: Use-Case Determination
        if not feat_compat["compatible"]:
            use_case = "REQUIRES_ADAPTER_DEVELOPMENT"
            status = "PENDING_ADAPTER"
            recs.append("Sensor adapter development required before ingestion into model pipeline.")
        elif not ref_avail:
            use_case = "INFERENCE_ONLY"
            status = "VALIDATED_INFERENCE_ONLY"
            recs.append("No independent ground-truth labels available. Dataset suitable for inference only; training is prohibited.")
        else:
            use_case = "REGIONAL_AND_MULTI_REGION_TRAINING"
            status = "VALIDATED_FOR_TRAINING"
            recs.append("Dataset satisfies sensor compatibility and reference label availability. Eligible for spatial block partitioning.")

        return IntakeAssessment(
            input_path=str(file_path),
            file_exists=True,
            file_size_bytes=file_size,
            sha256_checksum=sha256_val,
            sensor_identified=sensor,
            product_type_identified=prod_type,
            acquisition_date=acq_date,
            geographical_coverage=geo_cov,
            crs_identified=crs_str,
            spatial_resolution_m=res_m,
            raster_dimensions=dims,
            band_count=bands,
            feature_compatibility=feat_compat,
            reference_labels_available=ref_avail,
            use_case_determination=use_case,
            intake_status=status,
            recommendations=recs,
        )


def main():
    parser = argparse.ArgumentParser(description="Earth Pulse Incoming Dataset Intake & Readiness Validator")
    parser.add_argument("--file", required=True, help="Path to incoming satellite dataset file")
    parser.add_argument("--region-hint", default=None, help="Hint for target geographic region")
    parser.add_argument("--sensor-hint", default=None, help="Hint for sensor (e.g. sentinel1, nisar)")
    parser.add_argument("--reference-labels", default=None, help="Path to independent reference ground truth")
    parser.add_argument("--out-json", default=None, help="Path to save intake JSON report")

    args = parser.parse_args()

    pipeline = DatasetIntakePipeline()
    assessment = pipeline.inspect_dataset(
        file_path=Path(args.file),
        region_hint=args.region_hint,
        sensor_hint=args.sensor_hint,
        reference_label_path=Path(args.reference_labels) if args.reference_labels else None,
    )

    print("\n" + "=" * 70)
    print("EARTH PULSE INCOMING DATASET INTAKE ASSESSMENT REPORT")
    print("=" * 70)
    print(f"File Path:       {assessment.input_path}")
    print(f"File Size:       {assessment.file_size_bytes:,} bytes")
    print(f"SHA-256:         {assessment.sha256_checksum}")
    print(f"Sensor:          {assessment.sensor_identified}")
    print(f"Product Type:    {assessment.product_type_identified}")
    print(f"Acquisition:     {assessment.acquisition_date or 'N/A'}")
    print(f"CRS:             {assessment.crs_identified or 'N/A'}")
    print(f"Resolution:      {assessment.spatial_resolution_m or 'N/A'}")
    print(f"Dimensions:      {assessment.raster_dimensions or 'N/A'}")
    print(f"Compatibility:   {assessment.feature_compatibility}")
    print(f"Reference SCL:   {assessment.reference_labels_available}")
    print(f"Use Case:        {assessment.use_case_determination}")
    print(f"Intake Status:   {assessment.intake_status}")
    print("-" * 70)
    print("Recommendations:")
    for r in assessment.recommendations:
        print(f"  * {r}")
    print("=" * 70 + "\n")

    if args.out_json:
        out_p = Path(args.out_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(assessment.to_dict(), f, indent=2)
        print(f"Saved assessment report to: {out_p}")


if __name__ == "__main__":
    main()

