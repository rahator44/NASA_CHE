"""
Earth Pulse Prediction Record & Explainability Interface
Standardizes prediction metadata retention for future Phase 7B Explainable AI (SHAP) attributions.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class PredictionRecord:
    """
    Encapsulates a model prediction alongside its input features, spatial context, and provenance.
    Enables region-specific SHAP feature attributions and individual sample inspection in Phase 7B.
    
    Scientific Governance Notice:
      Model feature importance and local attribution weights quantify statistical feature influence
      within tree split pathways; they do NOT establish physical or geomorphic causation.
    """
    model_version: str
    region_id: str
    dataset_id: str
    feature_schema_version: str
    feature_names: List[str]
    feature_values: List[float]
    prediction_probability: float
    binary_prediction: int
    decision_threshold: float
    pixel_row: Optional[int] = None
    pixel_col: Optional[int] = None
    utm_x: Optional[float] = None
    utm_y: Optional[float] = None
    ground_truth_scl: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PredictionRecord":
        return cls(**data)


class ExplainabilityBatchBuffer:
    """
    Collects and serializes prediction records for downstream Phase 7B explainability analysis.
    """

    def __init__(
        self,
        model_version: str,
        region_id: str,
        dataset_id: str,
        feature_schema_version: str = "1.0.0",
        decision_threshold: float = 0.35,
    ):
        self.model_version = model_version
        self.region_id = region_id
        self.dataset_id = dataset_id
        self.feature_schema_version = feature_schema_version
        self.decision_threshold = decision_threshold
        self.records: List[PredictionRecord] = []

    def add_prediction(
        self,
        feature_names: List[str],
        feature_values: List[float],
        prediction_probability: float,
        pixel_row: Optional[int] = None,
        pixel_col: Optional[int] = None,
        utm_x: Optional[float] = None,
        utm_y: Optional[float] = None,
        ground_truth_scl: Optional[int] = None,
    ) -> PredictionRecord:
        """Appends an individual prediction record."""
        binary_pred = int(prediction_probability >= self.decision_threshold)
        rec = PredictionRecord(
            model_version=self.model_version,
            region_id=self.region_id,
            dataset_id=self.dataset_id,
            feature_schema_version=self.feature_schema_version,
            feature_names=feature_names,
            feature_values=[float(v) for v in feature_values],
            prediction_probability=float(prediction_probability),
            binary_prediction=binary_pred,
            decision_threshold=self.decision_threshold,
            pixel_row=pixel_row,
            pixel_col=pixel_col,
            utm_x=utm_x,
            utm_y=utm_y,
            ground_truth_scl=ground_truth_scl,
        )
        self.records.append(rec)
        return rec

    def to_dataframe(self) -> pd.DataFrame:
        """Converts accumulated records to a flattened pandas DataFrame ready for SHAP."""
        if not self.records:
            return pd.DataFrame()

        rows = []
        for r in self.records:
            row_dict = {
                "model_version": r.model_version,
                "region_id": r.region_id,
                "dataset_id": r.dataset_id,
                "feature_schema_version": r.feature_schema_version,
                "prediction_probability": r.prediction_probability,
                "binary_prediction": r.binary_prediction,
                "decision_threshold": r.decision_threshold,
                "pixel_row": r.pixel_row,
                "pixel_col": r.pixel_col,
                "utm_x": r.utm_x,
                "utm_y": r.utm_y,
                "ground_truth_scl": r.ground_truth_scl,
            }
            # Unpack feature values as columns
            for fn, fv in zip(r.feature_names, r.feature_values):
                row_dict[fn] = fv
            rows.append(row_dict)

        return pd.DataFrame(rows)

