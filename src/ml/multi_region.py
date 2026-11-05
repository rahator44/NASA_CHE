"""
Earth Pulse Multi-Region Strategy and Spatially Grouped Partitioning
Enforces spatial block isolation and zero spatial leakage across single-region, multi-region,
and cross-region transfer machine learning experiments.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


class ExperimentType(str, Enum):
    REGIONAL = "REGIONAL"                      # Single configured region
    MULTI_REGION = "MULTI_REGION"              # Multiple regions pooled with block stratification
    CROSS_REGION_TRANSFER = "CROSS_REGION"    # Train on Region A, test on Region B


class MultiRegionDatasetManager:
    """
    Manages regional datasets, spatial block isolation, and regional performance reporting.
    """

    @staticmethod
    def create_composite_block_id(region_id: str, block_id: Any) -> str:
        """
        Creates a globally unique composite block ID to prevent collision across regions.
        e.g., 'jamuna_sirajganj:block_12_45'
        """
        return f"{region_id}:{str(block_id)}"

    @staticmethod
    def partition_samples(
        df_samples: pd.DataFrame,
        experiment_type: ExperimentType = ExperimentType.REGIONAL,
        train_regions: Optional[List[str]] = None,
        test_regions: Optional[List[str]] = None,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20,
        random_seed: int = 42,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Partitions samples with guaranteed zero spatial leakage.
        Blocks are treated as atomic indivisible spatial units.
        """
        if df_samples.empty:
            return df_samples.copy(), df_samples.copy(), df_samples.copy()

        if "region_id" not in df_samples.columns:
            raise ValueError("df_samples must contain 'region_id' column.")
        if "block_id" not in df_samples.columns:
            raise ValueError("df_samples must contain 'block_id' column.")

        # Ensure composite block id
        if "composite_block_id" not in df_samples.columns:
            df = df_samples.copy()
            df["composite_block_id"] = [
                f"{r}:{b}" for r, b in zip(df["region_id"], df["block_id"])
            ]
        else:
            df = df_samples.copy()

        rng = np.random.RandomState(random_seed)

        if experiment_type == ExperimentType.CROSS_REGION_TRANSFER:
            if not train_regions or not test_regions:
                raise ValueError("CROSS_REGION experiment requires explicit train_regions and test_regions.")
            
            # Verify no overlap between train and test regions
            overlap = set(train_regions).intersection(set(test_regions))
            if overlap:
                raise ValueError(f"Cross-region transfer violated: Overlapping regions {overlap}.")

            train_val_df = df[df["region_id"].isin(train_regions)].copy()
            test_df = df[df["region_id"].isin(test_regions)].copy()

            # Split train_val_df into train and validation by spatial block
            train_val_blocks = train_val_df["composite_block_id"].unique()
            rng.shuffle(train_val_blocks)
            n_val = int(len(train_val_blocks) * 0.25)
            val_blocks = set(train_val_blocks[:n_val])
            train_blocks = set(train_val_blocks[n_val:])

            train_df = train_val_df[train_val_df["composite_block_id"].isin(train_blocks)].copy()
            val_df = train_val_df[train_val_df["composite_block_id"].isin(val_blocks)].copy()

            return train_df, val_df, test_df

        elif experiment_type in (ExperimentType.REGIONAL, ExperimentType.MULTI_REGION):
            # Block-stratified grouped split per region
            train_blocks_all = set()
            val_blocks_all = set()
            test_blocks_all = set()

            for reg in df["region_id"].unique():
                reg_blocks = df[df["region_id"] == reg]["composite_block_id"].unique()
                rng.shuffle(reg_blocks)
                n_b = len(reg_blocks)
                n_tr = int(np.round(n_b * train_ratio))
                n_va = int(np.round(n_b * val_ratio))

                tr_b = reg_blocks[:n_tr]
                va_b = reg_blocks[n_tr:n_tr + n_va]
                te_b = reg_blocks[n_tr + n_va:]

                train_blocks_all.update(tr_b)
                val_blocks_all.update(va_b)
                test_blocks_all.update(te_b)

            train_df = df[df["composite_block_id"].isin(train_blocks_all)].copy()
            val_df = df[df["composite_block_id"].isin(val_blocks_all)].copy()
            test_df = df[df["composite_block_id"].isin(test_blocks_all)].copy()

            # Assert zero leakage
            assert len(train_blocks_all.intersection(val_blocks_all)) == 0, "Spatial leakage between Train and Val!"
            assert len(train_blocks_all.intersection(test_blocks_all)) == 0, "Spatial leakage between Train and Test!"
            assert len(val_blocks_all.intersection(test_blocks_all)) == 0, "Spatial leakage between Val and Test!"

            return train_df, val_df, test_df

        else:
            raise ValueError(f"Unknown experiment type: {experiment_type}")

    @staticmethod
    def audit_regional_sample_distribution(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Audits sample balance across regions to ensure no single region silently dominates.
        """
        if df.empty or "region_id" not in df.columns:
            return {"total_samples": 0, "regions": {}}

        total = len(df)
        counts = df["region_id"].value_counts().to_dict()
        fractions = {r: count / total for r, count in counts.items()}

        dominating_region = None
        for r, frac in fractions.items():
            if frac > 0.70 and len(counts) > 1:
                dominating_region = r

        return {
            "total_samples": total,
            "regional_counts": counts,
            "regional_fractions": fractions,
            "is_imbalanced": dominating_region is not None,
            "dominating_region": dominating_region,
            "warning": (
                f"Region '{dominating_region}' constitutes >70% of dataset ({fractions.get(dominating_region, 0)*100:.1f}%). "
                "Regional weighting or subsampling is recommended."
                if dominating_region else None
            )
        }

