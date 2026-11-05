"""
Riverbank Migration & Displacement API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class RiverbankSummaryResponse(BaseModel):
    region_id: str
    total_transects_evaluated: int
    valid_transects_count: int
    ambiguous_transects_count: int
    valid_transect_fraction_pct: float
    mean_west_displacement_m: float
    mean_east_displacement_m: float
    mean_channel_width_change_m: float
    provisional_detection_range_m: str
    morphological_behavior: str
    scientific_readiness_status: str
    hydrodynamic_caveat: str


class TransectItem(BaseModel):
    transect_id: int
    station_m: float
    origin_utm: List[float]
    terminus_utm: List[float]
    bearing_deg: float
    is_valid: bool
    ambiguity_flag: Optional[str] = None
    west_bank_displacement_m: Optional[float] = None
    east_bank_displacement_m: Optional[float] = None
    channel_width_june_m: Optional[float] = None
    channel_width_july_m: Optional[float] = None
    net_width_change_m: Optional[float] = None


class TransectsListResponse(BaseModel):
    region_id: str
    total_count: int
    valid_count: int
    ambiguous_count: int
    transects: List[TransectItem]


class DisplacementStats(BaseModel):
    mean_m: float
    std_m: float
    median_m: float
    iqr_m: float
    p10_m: float
    p90_m: float
    min_m: float
    max_m: float
    bootstrap_ci_95: List[float]


class DisplacementResponse(BaseModel):
    region_id: str
    west_bank_expansion_stats: DisplacementStats
    east_bank_expansion_stats: DisplacementStats
    net_channel_width_change_stats: DisplacementStats
    detection_threshold_m: float
    unfiltered_vs_filtered_note: str


class ErosionCandidateZone(BaseModel):
    zone_type: str
    area_ha: float
    area_km2: float
    mean_displacement_m: float
    geomorphic_classification: str
    certainty_level: str
    description: str


class ErosionCandidatesResponse(BaseModel):
    region_id: str
    candidate_zones: List[ErosionCandidateZone]
    bre_embankment_influence_note: str


class RiverbankUncertaintyResponse(BaseModel):
    region_id: str
    quadrature_uncertainty_budget: Dict[str, float]
    total_displacement_uncertainty_m: float
    minimum_resolvable_displacement_m: float
    spatial_autocorrelation_decorrelation_length_m: float
    scientific_caveats: List[str]

