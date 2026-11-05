"""
Earth Pulse Reusable Dataset Manifest & Provenance Registry
Manages standardized metadata and cryptographic provenance across multi-region SAR and optical datasets.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional
import hashlib
import json

DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data/metadata/dataset_manifest.json"


@dataclass
class DatasetRecord:
    dataset_id: str
    region_id: str
    sensor: str
    product_type: str
    acquisition_date: str
    polarization: List[str]
    spatial_resolution_m: float
    crs: str
    source_path: str
    reference_label_availability: bool
    quality_status: str
    sha256: str
    processing_version: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetRecord":
        required_fields = [
            "dataset_id", "region_id", "sensor", "product_type",
            "acquisition_date", "polarization", "spatial_resolution_m",
            "crs", "source_path", "reference_label_availability",
            "quality_status", "sha256", "processing_version"
        ]
        for f in required_fields:
            if f not in data:
                raise ValueError(f"Missing mandatory field '{f}' in dataset manifest record.")
        return cls(**{k: data[k] for k in required_fields})


class DatasetManifest:
    """Manages collection of dataset records with query, verification, and persistence capabilities."""

    def __init__(self, manifest_path: Optional[Path] = None):
        self.manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
        self.records: Dict[str, DatasetRecord] = {}
        if self.manifest_path.exists():
            self.load()

    def add_record(self, record: DatasetRecord) -> None:
        """Adds or updates a dataset record."""
        self.records[record.dataset_id] = record

    def get_record(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Retrieves a record by its identifier."""
        return self.records.get(dataset_id)

    def filter(
        self,
        region_id: Optional[str] = None,
        sensor: Optional[str] = None,
        has_reference: Optional[bool] = None,
        quality_status: Optional[str] = None,
    ) -> List[DatasetRecord]:
        """Queries records by region, sensor, reference availability, or quality status."""
        results = []
        for r in self.records.values():
            if region_id and r.region_id != region_id:
                continue
            if sensor and r.sensor != sensor:
                continue
            if has_reference is not None and r.reference_label_availability != has_reference:
                continue
            if quality_status and r.quality_status != quality_status:
                continue
            results.append(r)
        return results

    def verify_file_checksum(self, dataset_id: str, base_dir: Optional[Path] = None) -> bool:
        """Verifies that the file exists on disk and matches the registered SHA-256."""
        rec = self.get_record(dataset_id)
        if not rec:
            raise KeyError(f"Dataset {dataset_id} not found in manifest.")
        
        root = base_dir or self.manifest_path.parent.parent.parent
        full_path = (root / rec.source_path).resolve()
        if not full_path.exists():
            return False

        hasher = hashlib.sha256()
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest() == rec.sha256

    def save(self, target_path: Optional[Path] = None) -> None:
        """Saves the manifest to JSON."""
        dest = target_path or self.manifest_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": "Earth Pulse Multi-Region Dataset Manifest",
            "version": "1.0.0",
            "datasets": [r.to_dict() for r in self.records.values()]
        }
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load(self, source_path: Optional[Path] = None) -> None:
        """Loads the manifest from JSON."""
        src = source_path or self.manifest_path
        with open(src, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.records = {}
        for item in payload.get("datasets", []):
            rec = DatasetRecord.from_dict(item)
            self.records[rec.dataset_id] = rec

