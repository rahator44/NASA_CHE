"""
Dataset & Provenance Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.backend.config import settings
from src.backend.database.database import get_db_connection


class DatasetService:
    @staticmethod
    def _load_manifest() -> List[Dict[str, Any]]:
        manifest_path = settings.METADATA_DIR / "dataset_manifest.json"
        if not manifest_path.exists():
            return []
        with open(manifest_path, "r") as f:
            data = json.load(f)
        return data.get("datasets", [])

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Computes genuine SHA-256 digest in 1 MB stream chunks."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1048576):
                hasher.update(chunk)
        return hasher.hexdigest().lower()

    @classmethod
    def verify_dataset(cls, dataset_id: str, force: bool = False) -> Dict[str, Any]:
        """Cryptographically verifies a single dataset against its expected SHA-256 and records state in SQLite."""
        raw_list = cls._load_manifest()
        target = None
        for item in raw_list:
            if item.get("dataset_id") == dataset_id:
                target = item
                break

        if not target:
            return {
                "dataset_id": dataset_id,
                "status": "NOT_FOUND",
                "checksum_verified": False,
            }

        rel_path = target.get("relative_path") or target.get("source_path") or ""
        try:
            full_path = settings.resolve_data_path(rel_path) if rel_path else None
        except ValueError:
            full_path = None

        if not full_path or not full_path.exists():
            return {
                "dataset_id": dataset_id,
                "status": "FILE_MISSING",
                "checksum_verified": False,
            }

        stat = full_path.stat()
        expected_sha = (target.get("sha256") or "").lower()

        # Check if existing verification in SQLite matches current mtime and size unless force=True
        if not force:
            try:
                with get_db_connection() as conn:
                    row = conn.execute(
                        "SELECT verified_sha256, file_mtime, file_size, status FROM dataset_verifications WHERE dataset_id = ?",
                        (dataset_id,)
                    ).fetchone()
                    if row and row["file_mtime"] == stat.st_mtime and row["file_size"] == stat.st_size:
                        return {
                            "dataset_id": dataset_id,
                            "path": rel_path,
                            "status": "VERIFIED_INTACT" if row["status"] == "VERIFIED" else "HASH_MISMATCH",
                            "checksum_verified": (row["status"] == "VERIFIED"),
                            "sha256": row["verified_sha256"],
                            "valid": (row["status"] == "VERIFIED"),
                        }
            except Exception:
                pass

        # Compute genuine SHA-256
        actual_sha = cls.compute_sha256(full_path)
        is_valid = bool(expected_sha and actual_sha == expected_sha)
        status_str = "VERIFIED" if is_valid else "CHECKSUM_MISMATCH"
        now_str = datetime.now(timezone.utc).isoformat()

        try:
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO dataset_verifications
                    (dataset_id, verified_sha256, file_mtime, file_size, verified_at, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (dataset_id, actual_sha, stat.st_mtime, stat.st_size, now_str, status_str))
                conn.commit()
        except Exception:
            pass

        return {
            "dataset_id": dataset_id,
            "path": rel_path,
            "status": "VERIFIED_INTACT" if is_valid else "HASH_MISMATCH",
            "checksum_verified": is_valid,
            "sha256": actual_sha,
            "expected_sha": expected_sha,
            "valid": is_valid,
        }

    @classmethod
    def verify_all_datasets(cls, force: bool = False) -> Dict[str, Any]:
        """Verifies all datasets registered in dataset_manifest.json and records results."""
        manifest = cls._load_manifest()
        results = []
        all_valid = True
        verified_count = 0

        for item in manifest:
            did = item["dataset_id"]
            res = cls.verify_dataset(did, force=force)
            if not res.get("checksum_verified", False):
                all_valid = False
            else:
                verified_count += 1
            results.append(res)

        return {
            "total_count": len(manifest),
            "verified_count": verified_count,
            "all_valid": all_valid,
            "details": results,
        }

    @classmethod
    def _get_verification_status(cls, dataset_id: str, item: Dict[str, Any], full_path: Optional[Path]) -> Tuple[bool, str]:
        """Retrieves explicit verification state backed by genuine SHA-256 comparison and mtime invalidation."""
        if not full_path or not full_path.exists():
            return False, "FILE_MISSING"

        stat = full_path.stat()
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT verified_sha256, file_mtime, file_size, status FROM dataset_verifications WHERE dataset_id = ?",
                    (dataset_id,)
                ).fetchone()

            if not row:
                return False, "UNVERIFIED"

            if row["file_mtime"] == stat.st_mtime and row["file_size"] == stat.st_size:
                if row["status"] == "VERIFIED":
                    return True, "VERIFIED"
                else:
                    return False, "CHECKSUM_MISMATCH"
            else:
                # File was modified after verification
                return False, "UNVERIFIED_MODIFIED"
        except Exception:
            return False, "UNVERIFIED"

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

            did = item["dataset_id"]
            rel_path = item.get("relative_path") or item.get("source_path") or ""
            try:
                full_path = settings.resolve_data_path(rel_path) if rel_path else None
            except ValueError:
                full_path = None

            chk_verified, q_status = cls._get_verification_status(did, item, full_path)

            results.append({
                "dataset_id": did,
                "region_id": item.get("region_id", "jamuna_sirajganj"),
                "sensor": item.get("sensor", "Sentinel-1"),
                "satellite": item.get("satellite", "Sentinel-1A"),
                "acquisition_date": item.get("acquisition_date", ""),
                "product_type": item.get("product_type", "GRD"),
                "processing_level": item.get("processing_level", "Level-1"),
                "polarization": item.get("polarization", "VV+VH"),
                "spatial_resolution_m": float(item.get("spatial_resolution_m", 20.0)),
                "crs": item.get("crs", "EPSG:32645"),
                "quality_status": q_status,
                "checksum_verified": chk_verified,
                "sha256": item.get("sha256"),
                "file_format": item.get("file_format", "GeoTIFF"),
                "relative_path": rel_path,
            })

        return results

    @classmethod
    def get_dataset(cls, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Strict exact lookup of registered dataset by its full dataset_id. Substring matches are rejected."""
        raw_list = cls._load_manifest()
        for item in raw_list:
            did = item.get("dataset_id", "")
            if did == dataset_id:  # Strict exact match only
                rel_path = item.get("relative_path") or item.get("source_path") or ""
                try:
                    full_path = settings.resolve_data_path(rel_path) if rel_path else None
                except ValueError:
                    full_path = None

                chk_verified, q_status = cls._get_verification_status(did, item, full_path)

                return {
                    "dataset_id": did,
                    "region_id": item.get("region_id", "jamuna_sirajganj"),
                    "sensor": item.get("sensor", "Sentinel-1"),
                    "satellite": item.get("satellite", "Sentinel-1A"),
                    "acquisition_date": item.get("acquisition_date", ""),
                    "product_type": item.get("product_type", "GRD"),
                    "processing_level": item.get("processing_level", "Level-1"),
                    "polarization": item.get("polarization", "VV+VH"),
                    "spatial_resolution_m": float(item.get("spatial_resolution_m", 20.0)),
                    "crs": item.get("crs", "EPSG:32645"),
                    "quality_status": q_status,
                    "checksum_verified": chk_verified,
                    "sha256": item.get("sha256"),
                    "file_format": item.get("file_format", "GeoTIFF"),
                    "relative_path": rel_path,
                }
        return None
