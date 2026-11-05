"""
Flood and Surface-Water Change API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


class EpochWaterArea(BaseModel):
    epoch_name: str
    acquisition_date: str
    hydrological_condition: str
    candidate_water_cells: int
    candidate_water_area_ha: float
    candidate_water_area_km2: float
    candidate_water_pct_valid: float
    candidate_water_pct_aoi: float
    vv_threshold_db: float
    vh_threshold_db: float


class FloodSummaryResponse(BaseModel):
    region_id: str
    methodology: Union[str, Dict[str, Any]]
    pre_monsoon_epoch: EpochWaterArea
    flood_observation_epoch: EpochWaterArea
    monsoon_crest_epoch: Optional[EpochWaterArea] = None  # Preserved for backward compatibility
    net_candidate_water_change_ha: float
    net_candidate_water_change_km2: float
    whole_epoch_unmasked_delta_ha: Optional[float] = None
    whole_epoch_unmasked_delta_km2: Optional[float] = None
    asymmetric_exclusions_gap_ha: Optional[float] = None
    accounting_note: str


class TransitionClass(BaseModel):
    class_id: int
    class_name: str
    pixel_count: int
    area_ha: float
    area_km2: float
    percentage_of_valid_domain: float
    description: str


class FloodTransitionsResponse(BaseModel):
    region_id: str
    common_valid_domain_cells: int
    common_valid_domain_ha: float
    common_valid_domain_km2: float
    transitions: List[TransitionClass]
    net_inundation_balance_ha: float
    accounting_rule: str


class FloodCluster(BaseModel):
    cluster_id: int
    area_ha: float
    area_km2: float
    cell_count: int
    centroid_utm: List[float]
    geographic_zone: str
    description: str


class FloodClustersResponse(BaseModel):
    region_id: str
    total_clusters_count: int
    total_clustered_area_ha: float
    major_clusters: List[FloodCluster]


class FloodUncertaintyResponse(BaseModel):
    region_id: str
    radar_shadow_exclusion_ha: float
    layover_exclusion_ha: float
    water_lookalike_exclusion_ha: float
    total_indeterminate_ha: float
    classification_confidence: Dict[str, str]
    quality_standards: List[str]
