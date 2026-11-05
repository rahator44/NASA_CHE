"""
Earth Pulse Lightweight Model Registry & Versioning System
Tracks multi-region model versions, hyperparameters, evaluation metrics, and promotion criteria.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import json
from datetime import datetime, timezone

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "models/model_registry.json"


@dataclass
class ModelRegistryEntry:
    model_id: str
    version: str
    region_coverage: List[str]
    sensor_compatibility: List[str]
    feature_schema_version: str
    training_dataset_identifiers: List[str]
    training_dates: List[str]
    hyperparameters: Dict[str, Any]
    random_seed: int
    validation_metrics: Dict[str, float]
    held_out_test_metrics: Dict[str, float]
    model_artifact_path: str
    model_artifact_sha256: str
    creation_date: str
    status: str = "CANDIDATE"
    promotion_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRegistryEntry":
        return cls(**data)


class ModelRegistry:
    """
    Manages versioned models, preventing accidental overwriting and enforcing promotion criteria.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH
        self.models: Dict[str, ModelRegistryEntry] = {}
        if self.registry_path.exists():
            self.load()

    def register_model(
        self,
        entry: ModelRegistryEntry,
        verify_artifact: bool = True,
        base_dir: Optional[Path] = None,
    ) -> None:
        """
        Registers a new model version. Fails if model_id already exists to prevent accidental overwrite.
        """
        if entry.model_id in self.models:
            raise ValueError(
                f"Model '{entry.model_id}' is already registered. Overwriting validated models is forbidden. "
                "Increment model version or use a new identifier."
            )

        if verify_artifact:
            root = base_dir or self.registry_path.parent.parent
            art_path = (root / entry.model_artifact_path).resolve()
            if not art_path.exists():
                raise FileNotFoundError(f"Model artifact not found at: {art_path}")
            
            hasher = hashlib.sha256()
            with open(art_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            calc_hash = hasher.hexdigest()
            if calc_hash != entry.model_artifact_sha256:
                raise ValueError(
                    f"Artifact SHA-256 mismatch for {entry.model_id}: expected {entry.model_artifact_sha256}, got {calc_hash}"
                )

        self.models[entry.model_id] = entry

    def get_model(self, model_id: str) -> Optional[ModelRegistryEntry]:
        return self.models.get(model_id)

    def list_models(
        self,
        region_id: Optional[str] = None,
        sensor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ModelRegistryEntry]:
        results = []
        for m in self.models.values():
            if region_id and region_id not in m.region_coverage:
                continue
            if sensor and sensor not in m.sensor_compatibility:
                continue
            if status and m.status != status:
                continue
            results.append(m)
        return results

    def promote_model(
        self,
        model_id: str,
        criteria: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Evaluates a model against explicit quantitative promotion criteria.
        Default criteria:
          - test_precision >= 0.55
          - test_recall >= 0.70
          - test_specificity >= 0.70
          - test_f1 >= 0.60
        """
        entry = self.get_model(model_id)
        if not entry:
            raise KeyError(f"Model '{model_id}' not found in registry.")

        default_criteria = {
            "precision": 0.55,
            "recall": 0.70,
            "specificity": 0.70,
            "f1_score": 0.60,
        }
        active_criteria = criteria or default_criteria

        failures = []
        metrics = entry.held_out_test_metrics

        for metric_name, target in active_criteria.items():
            val = metrics.get(metric_name)
            if val is None:
                failures.append(f"Missing required metric '{metric_name}' in test evaluation.")
            elif val < target:
                failures.append(f"Metric '{metric_name}' = {val:.4f} is below promotion threshold {target:.4f}.")

        if failures:
            entry.status = "RETAINED_AS_PROBABILITY_LAYER"
            entry.promotion_notes = "Promotion to primary operational baseline rejected: " + "; ".join(failures)
            return False, failures
        else:
            entry.status = "PROMOTED"
            entry.promotion_notes = f"Promoted to primary operational classifier on {datetime.now(timezone.utc).isoformat()}."
            return True, []

    def save(self, target_path: Optional[Path] = None) -> None:
        dest = target_path or self.registry_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": "Earth Pulse SAR Machine Learning Model Registry",
            "version": "1.0.0",
            "models": [m.to_dict() for m in self.models.values()]
        }
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load(self, source_path: Optional[Path] = None) -> None:
        src = source_path or self.registry_path
        with open(src, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.models = {}
        for item in payload.get("models", []):
            entry = ModelRegistryEntry.from_dict(item)
            self.models[entry.model_id] = entry

