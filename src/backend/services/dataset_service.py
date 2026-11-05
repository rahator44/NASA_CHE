"""
Dataset & Provenance Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.backend.config import settings


class DatasetService:
    @staticmethod
    def _load_manifest() -> List[Dict[str, Any]]:
        manifest_path = settings.METADATA_DIR / "dataset_manifest.json"
        if not manifest_path.exists():
            return []
        with open(manifest_path, "r") as f:
            data = json.load(f)
        return data.get("datasets", [])

    @classmethod
    def list_datasets(
        cls,
        region_id: Optional[str] = None,
        sensor: Optional[str] = None,
        acquisition_date: Optional[str] = None,
        product_type: Optional[str] = None,
        quality_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        raw_list = cls._load_manifest()
        results = []

        for item in raw_list:
            # Region filter
            if region_id and item.get("region_id") != region_id:
                continue
            # Sensor filter
            if sensor and item.get("sensor", "").lower() != sensor.lower():
                continue
            # Acquisition date filter (date prefix match)
            if acquisition_date and not item.get("acquisition_date", "").startswith(acquisition_date):
                continue
            # Product type filter
            if product_type and item.get("product_type", "").lower() != product_type.lower():
                continue
            # Quality status filter
            if quality_status and item.get("quality_status", "").lower() != quality_status.lower():
                continue

            results.append({
                "dataset_id": item["dataset_id"],
                "region_id": item.get("region_id", "jamuna_sirajganj"),
                "sensor": item.get("sensor", "Sentinel-1"),
                "satellite": item.get("satellite", "Sentinel-1A"),
                "acquisition_date": item.get("acquisition_date", ""),
                "product_type": item.get("product_type", "GRD"),
                "processing_level": item.get("processing_level", "Level-1"),
                "polarization": item.get("polarization", "VV+VH"),
                "spatial_resolution_m": float(item.get("spatial_resolution_m", 20.0)),
                "crs": item.get("crs", "EPSG:32645"),
                "quality_status": item.get("quality_status", "VERIFIED"),
                "checksum_verified": bool(item.get("checksum_verified", True)),
                "sha256": item.get("sha256"),
                "file_format": item.get("file_format", "GeoTIFF"),
                "relative_path": item.get("relative_path") or item.get("source_path", ""),
            })

        return results

    @classmethod
    def get_dataset(cls, dataset_id: str) -> Optional[Dict[str, Any]]:
        raw_list = cls._load_manifest()
        for item in raw_list:
            did = item.get("dataset_id", "")
            if did == dataset_id or dataset_id in did:
                return {
                    "dataset_id": item["dataset_id"],
                    "region_id": item.get("region_id", "jamuna_sirajganj"),
                    "sensor": item.get("sensor", "Sentinel-1"),
                    "satellite": item.get("satellite", "Sentinel-1A"),
                    "acquisition_date": item.get("acquisition_date", ""),
                    "product_type": item.get("product_type", "GRD"),
                    "processing_level": item.get("processing_level", "Level-1"),
                    "polarization": item.get("polarization", "VV+VH"),
                    "spatial_resolution_m": float(item.get("spatial_resolution_m", 20.0)),
                    "crs": item.get("crs", "EPSG:32645"),
                    "quality_status": item.get("quality_status", "VERIFIED"),
                    "checksum_verified": bool(item.get("checksum_verified", True)),
                    "sha256": item.get("sha256"),
                    "file_format": item.get("file_format", "GeoTIFF"),
                    "relative_path": item.get("relative_path") or item.get("source_path", ""),
                }
        return None
