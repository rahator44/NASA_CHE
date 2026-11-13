/**
 * Earth Pulse SAR — Production Frontend API Contracts & Scientific Schemas
 * Directly aligned with FastAPI endpoints in src/backend/api/v1/endpoints/dynamic_analysis.py
 * and authoritative run artifacts (summary.json, visual_manifest.json, explanations.json).
 */

export interface ObservationMeta {
  scene_name: string;
  acquisition_time: string;
  water_area_km2: number;
  independent_observed_water_km2?: number;
  common_domain_water_km2?: number;
  threshold_vv_db: number;
  threshold_vh_db: number;
  note?: string;
}

export interface FloodTransitionsKm2 {
  persistent_water: number;
  newly_inundated: number;
  receded_water: number;
  persistent_non_water: number;
  indeterminate_floor: number;
  raster_polygon_area?: number;
  valid_comparison_area?: number;
  total_study_aoi?: number;
  bounding_box_area?: number;
  outside_polygon_nodata_area?: number;
  net_candidate_water_change: number;
  gross_inundation?: number;
  gross_recession?: number;
}

export interface FloodReconciliation {
  net_equals_inundation_minus_recession: boolean;
  water_t1_pixels?: number;
  water_t2_pixels?: number;
  net_change_pixels?: number;
  calculated_net_change_km2?: number;
  reconciliation_discrepancy_km2?: number;
}

export interface TransectDiagnostic {
  transect_row?: number;
  northing_utm?: number;
  reason?: string;
  channel_width_baseline_m?: number;
  channel_width_change_m?: number;
  apparent_left_disp_m?: number;
  apparent_right_disp_m?: number;
  left_bank_displacement_m?: number;
  right_bank_displacement_m?: number;
  iou?: number;
  has_detached_water?: boolean;
  is_reliable?: boolean;
}

export interface RiverbankDynamics {
  status?: string;
  message?: string;
  channel_correspondence_status?: string;
  evaluated_transects: number;
  valid_migration_transects: number;
  reliable_transects_count?: number;
  unqualified_transects_count?: number;
  unqualified_transects?: TransectDiagnostic[];
  external_bank_expansion_km2?: number;
  internal_char_submergence_km2?: number;
  channel_water_km2?: number;
  mean_left_bank_displacement_m?: number | null;
  mean_right_bank_displacement_m?: number | null;
  max_bank_displacement_m?: number | null;
  sample_transects?: TransectDiagnostic[];
}

export interface ExplanationAttributions {
  vv_db: number;
  vh_db: number;
  vv_minus_vh_db: number;
  cross_pol_ratio: number;
  texture_vv: number;
  texture_vh: number;
}

export interface SampleExplanation {
  base_value: number;
  prediction_probability: number;
  attributions: ExplanationAttributions;
  sum_attributions: number;
  additivity_error: number;
  is_additive: boolean;
  baseline_mode: string;
}

export interface AiEvaluation {
  model_id: string;
  sample_evaluated: number;
  mean_water_probability: number;
  additivity_verified: boolean;
  sample_explanations?: SampleExplanation[];
}

export interface StudyAoi {
  wkt: string;
  geometric_vector_area_km2?: number;
  raster_polygon_area_km2?: number;
  bounding_box_area_km2?: number;
  common_valid_domain_km2?: number;
  pixel_area_km2?: number;
  discretization_pct?: number;
  area_definitions_note?: string;
  analyzed_pixel_area_km2?: number;
  total_area_km2?: number;
  valid_comparison_km2?: number;
}

export interface RunSummary {
  run_id: string;
  status: string;
  completed_at?: string;
  study_aoi: StudyAoi;
  observations: {
    baseline: ObservationMeta;
    change: ObservationMeta;
  };
  flood_transitions_km2: FloodTransitionsKm2;
  flood_reconciliation?: FloodReconciliation;
  riverbank_dynamics: RiverbankDynamics;
  ai_evaluation?: AiEvaluation;
}

export interface ManifestLegendClass {
  value: number;
  label: string;
  color: string;
  area_km2?: number | null;
}

export interface ManifestLegend {
  type: 'categorical' | 'continuous';
  classes?: ManifestLegendClass[];
  min_db?: number;
  max_db?: number;
  units?: string;
  min?: number;
  max?: number;
  decision_threshold?: number;
  colormap?: string;
}

export interface VisualLayer {
  layer_id: string;
  title: string;
  type: string;
  tile_url_template?: string | null;
  preview_png_url?: string;
  download_geotiff_url?: string;
  legend?: ManifestLegend;
}

export interface VisualManifest {
  run_id: string;
  status: string;
  completed_at?: string;
  geographic_bounds: {
    epsg4326: [number, number, number, number]; // [min_lon, min_lat, max_lon, max_lat]
    epsg32645?: [number, number, number, number];
    center?: { lon: number; lat: number };
  };
  pixel_spacing_m?: [number, number];
  observations?: Record<string, unknown>;
  layers: VisualLayer[];
  vectors?: Array<Record<string, unknown>>;
  scientific_provenance?: Record<string, unknown>;
}

export interface ExplanationsResponse {
  model_id: string;
  sample_evaluated: number;
  mean_water_probability: number;
  additivity_verified: boolean;
  sample_explanations: SampleExplanation[];
}

export interface LoadedRun {
  runId: string;
  summary: RunSummary;
  manifest: VisualManifest;
  explanations?: ExplanationsResponse;
}

export interface AnalysisRunRecord {
  run_id: string;
  analysis_type: string;
  region_id: string;
  status: string;
  executed_at?: string;
  completed_at?: string | null;
  parameters: Record<string, unknown>;
  outputs: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface CampaignOption {
  id: string;
  label: string;
  dateRange: string;
  archived: boolean;
  description: string;
  /** Net change published on this record only. Never copied from another run. */
  netChangeKm2: number | null;
  status: string;
  /** True when the id was requested but is not a catalogue record with outputs. */
  unavailable?: boolean;
}


// ============================================================================
// DYNAMIC SATELLITE ANALYSIS & CATALOG SEARCH CONTRACTS
// ============================================================================

export interface Sentinel1Scene {
  scene_name: string;
  acquisition_time: string;
  platform?: string;
  relative_orbit?: number;
  orbit_direction?: 'ASCENDING' | 'DESCENDING' | string;
  polarization?: string;
  beam_mode?: string;
  processing_level?: string;
  aoi_coverage_pct?: number;
  download_url?: string;
  bytes?: number;
}

export interface PairMetrics {
  flight_direction_match: boolean;
  track_match: boolean;
  polarization_match: boolean;
  beam_mode_match: boolean;
  processing_level_match: boolean;
  temporal_baseline_days: number | null;
  coverage_baseline_pct?: number | null;
  coverage_change_pct?: number | null;
}

export interface CompatiblePair {
  baseline: Sentinel1Scene;
  change: Sentinel1Scene;
  temporal_baseline_days: number | null;
  metrics: PairMetrics;
}

export interface CatalogSearchRequest {
  aoi_wkt: string;
  start_date: string;
  end_date: string;
  orbit_direction?: string | null;
  relative_orbit?: number | null;
  max_results?: number;
}

export interface CatalogSearchResponse {
  total_scenes: number;
  scenes: Sentinel1Scene[];
  compatible_pairs_count: number;
  compatible_pairs: CompatiblePair[];
}

export interface AnalysisCreateRequest {
  aoi_wkt: string;
  start_date: string;
  end_date: string;
  mode?: 'two_date_comparison' | 'multi_date_timeseries';
  parameters?: Record<string, unknown>;
  run_synchronously?: boolean;
}

export interface AnalysisJobStatus {
  run_id: string;
  status: 'CREATED' | 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  progress_pct: number;
  stage?: string;
  error?: string;
  completed_at?: string;
  request?: Record<string, unknown>;
  summary?: RunSummary;
}

export interface GeometryValidationResult {
  isValid: boolean;
  areaKm2: number;
  vertexCount: number;
  isContainedInStudyRegion: boolean;
  error?: string;
}
