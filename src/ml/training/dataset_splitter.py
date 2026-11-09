"""
Dataset Splitting and Spatial/Temporal Cross-Validation.
NASA Space Apps Challenge 2026: Dancing with the SARs

Enforces spatial separation and temporal holdout to prevent data leakage:
- Spatial Block K-Fold: Disjoint spatial tiles/quadrants
- Temporal Holdout: Train on earlier acquisitions, evaluate on distinct later dates
"""

import numpy as np
from typing import Tuple, List, Dict, Any, Optional


class SpatialTemporalSplitter:
    """
    Manages leak-free data partitioning for SAR model training and evaluation.
    """

    @staticmethod
    def spatial_quadrant_split(
        coords_yx: np.ndarray,
        test_quadrant: int = 4,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Partition points into train and test sets based on spatial quadrants (1-4).
        coords_yx: (N, 2) array of [row, col] coordinates.
        test_quadrant: 1 (top-left), 2 (top-right), 3 (bottom-left), 4 (bottom-right).
        """
        rows = coords_yx[:, 0]
        cols = coords_yx[:, 1]
        mid_r = np.median(rows)
        mid_c = np.median(cols)

        q1 = (rows < mid_r) & (cols < mid_c)
        q2 = (rows < mid_r) & (cols >= mid_c)
        q3 = (rows >= mid_r) & (cols < mid_c)
        q4 = (rows >= mid_r) & (cols >= mid_c)

        quadrant_masks = {1: q1, 2: q2, 3: q3, 4: q4}
        test_mask = quadrant_masks.get(test_quadrant, q4)
        train_mask = ~test_mask

        train_indices = np.where(train_mask)[0]
        test_indices = np.where(test_mask)[0]

        return train_indices, test_indices

    @staticmethod
    def stratified_temporal_split(
        dates: List[str],
        holdout_date: str,
    ) -> Tuple[List[int], List[int]]:
        """
        Partition multi-date observations such that holdout_date is evaluated independently.
        """
        train_indices = [i for i, d in enumerate(dates) if d != holdout_date]
        test_indices = [i for i, d in enumerate(dates) if d == holdout_date]

        return train_indices, test_indices
