"""
Earth Pulse Scientific Pipeline Package.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from src.pipeline.sentinel1_preprocess import (
    Sentinel1Preprocessor,
    find_snap_gpt_executable,
    validate_sar_raster,
    compare_rasters_for_validation,
)
from src.pipeline.water_classification import (
    DynamicWaterClassifier,
    vectorized_lee_filter,
    otsu_threshold_1d,
    otsu_threshold_2d,
)
from src.pipeline.change_detection import (
    DynamicChangeDetector,
    TRANS_PERSISTENT_WATER,
    TRANS_NEWLY_INUNDATED,
    TRANS_RECEDED_WATER,
    TRANS_PERSISTENT_NON_WATER,
    TRANS_INDETERMINATE,
    TRANS_NODATA_INVALID,
)
from src.pipeline.riverbank_analysis import (
    DynamicRiverbankAnalyzer,
)
from src.pipeline.feature_builder import (
    SARFeatureBuilder,
    FEATURE_NAMES,
)
from src.pipeline.time_series import (
    MultiDateTimeSeriesAnalyzer,
)
from src.pipeline.visualization import (
    ScientificVisualizer,
    COLOR_TRANSITIONS,
    COLOR_WATER_MASK,
)

__all__ = [
    "Sentinel1Preprocessor",
    "find_snap_gpt_executable",
    "validate_sar_raster",
    "compare_rasters_for_validation",
    "DynamicWaterClassifier",
    "vectorized_lee_filter",
    "otsu_threshold_1d",
    "otsu_threshold_2d",
    "DynamicChangeDetector",
    "TRANS_PERSISTENT_WATER",
    "TRANS_NEWLY_INUNDATED",
    "TRANS_RECEDED_WATER",
    "TRANS_PERSISTENT_NON_WATER",
    "TRANS_INDETERMINATE",
    "TRANS_NODATA_INVALID",
    "DynamicRiverbankAnalyzer",
    "SARFeatureBuilder",
    "FEATURE_NAMES",
    "MultiDateTimeSeriesAnalyzer",
    "ScientificVisualizer",
    "COLOR_TRANSITIONS",
    "COLOR_WATER_MASK",
]

