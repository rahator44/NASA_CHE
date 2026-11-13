/**
 * Earth Pulse SAR — Runtime Scientific Response Validation
 * Strictly validates responses from FastAPI endpoints against real observation schemas.
 * Rejects malformed responses and prevents silent runtime corruption or NaN display.
 */

import {
  RunSummary,
  VisualManifest,
  ExplanationsResponse,
  ObservationMeta,
  FloodTransitionsKm2,
  RiverbankDynamics,
  SampleExplanation,
  VisualLayer,
} from './types';

function isObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}

function isNumber(val: unknown): val is number {
  return typeof val === 'number' && Number.isFinite(val);
}

function isString(val: unknown): val is string {
  return typeof val === 'string';
}

function validateObservation(obj: unknown, label: string): ObservationMeta {
  if (!isObject(obj)) {
    throw new Error(`Invalid observation metadata for ${label}: expected object`);
  }
  if (!isString(obj.scene_name) || !obj.scene_name.trim()) {
    throw new Error(`Invalid observation metadata for ${label}: missing or empty scene_name`);
  }
  if (!isString(obj.acquisition_time) || !obj.acquisition_time.trim()) {
    throw new Error(`Invalid observation metadata for ${label}: missing or empty acquisition_time`);
  }
  if (!isNumber(obj.water_area_km2)) {
    throw new Error(`Invalid observation metadata for ${label}: water_area_km2 must be a valid number`);
  }
  if (!isNumber(obj.threshold_vv_db)) {
    throw new Error(`Invalid observation metadata for ${label}: threshold_vv_db must be a valid number`);
  }
  if (!isNumber(obj.threshold_vh_db)) {
    throw new Error(`Invalid observation metadata for ${label}: threshold_vh_db must be a valid number`);
  }

  return {
    scene_name: obj.scene_name,
    acquisition_time: obj.acquisition_time,
    water_area_km2: obj.water_area_km2,
    independent_observed_water_km2: isNumber(obj.independent_observed_water_km2)
      ? obj.independent_observed_water_km2
      : undefined,
    common_domain_water_km2: isNumber(obj.common_domain_water_km2)
      ? obj.common_domain_water_km2
      : undefined,
    threshold_vv_db: obj.threshold_vv_db,
    threshold_vh_db: obj.threshold_vh_db,
    note: isString(obj.note) ? obj.note : undefined,
  };
}

function validateFloodTransitions(obj: unknown): FloodTransitionsKm2 {
  if (!isObject(obj)) {
    throw new Error('Invalid flood transitions: expected object');
  }
  const requiredNumericFields: Array<keyof FloodTransitionsKm2> = [
    'persistent_water',
    'newly_inundated',
    'receded_water',
    'persistent_non_water',
    'indeterminate_floor',
    'net_candidate_water_change',
  ];

  for (const field of requiredNumericFields) {
    if (!isNumber(obj[field])) {
      throw new Error(`Invalid flood transitions: required field '${field}' is missing or not a valid number`);
    }
  }

  return {
    persistent_water: obj.persistent_water as number,
    newly_inundated: obj.newly_inundated as number,
    receded_water: obj.receded_water as number,
    persistent_non_water: obj.persistent_non_water as number,
    indeterminate_floor: obj.indeterminate_floor as number,
    net_candidate_water_change: obj.net_candidate_water_change as number,
    raster_polygon_area: isNumber(obj.raster_polygon_area) ? obj.raster_polygon_area : undefined,
    valid_comparison_area: isNumber(obj.valid_comparison_area) ? obj.valid_comparison_area : undefined,
    total_study_aoi: isNumber(obj.total_study_aoi) ? obj.total_study_aoi : undefined,
    bounding_box_area: isNumber(obj.bounding_box_area) ? obj.bounding_box_area : undefined,
    outside_polygon_nodata_area: isNumber(obj.outside_polygon_nodata_area)
      ? obj.outside_polygon_nodata_area
      : undefined,
    gross_inundation: isNumber(obj.gross_inundation) ? obj.gross_inundation : undefined,
    gross_recession: isNumber(obj.gross_recession) ? obj.gross_recession : undefined,
  };
}

function validateRiverbankDynamics(obj: unknown): RiverbankDynamics {
  if (!isObject(obj)) {
    throw new Error('Invalid riverbank dynamics: expected object');
  }
  if (!isNumber(obj.evaluated_transects)) {
    throw new Error("Invalid riverbank dynamics: 'evaluated_transects' must be a valid number");
  }
  if (!isNumber(obj.valid_migration_transects)) {
    throw new Error("Invalid riverbank dynamics: 'valid_migration_transects' must be a valid number");
  }

  return {
    status: isString(obj.status) ? obj.status : undefined,
    message: isString(obj.message) ? obj.message : undefined,
    channel_correspondence_status: isString(obj.channel_correspondence_status)
      ? obj.channel_correspondence_status
      : undefined,
    evaluated_transects: obj.evaluated_transects,
    valid_migration_transects: obj.valid_migration_transects,
    reliable_transects_count: isNumber(obj.reliable_transects_count) ? obj.reliable_transects_count : undefined,
    unqualified_transects_count: isNumber(obj.unqualified_transects_count)
      ? obj.unqualified_transects_count
      : undefined,
    unqualified_transects: Array.isArray(obj.unqualified_transects)
      ? (obj.unqualified_transects as any[])
      : undefined,
    external_bank_expansion_km2: isNumber(obj.external_bank_expansion_km2)
      ? obj.external_bank_expansion_km2
      : undefined,
    internal_char_submergence_km2: isNumber(obj.internal_char_submergence_km2)
      ? obj.internal_char_submergence_km2
      : undefined,
    channel_water_km2: isNumber(obj.channel_water_km2) ? obj.channel_water_km2 : undefined,
    mean_left_bank_displacement_m: isNumber(obj.mean_left_bank_displacement_m)
      ? obj.mean_left_bank_displacement_m
      : null,
    mean_right_bank_displacement_m: isNumber(obj.mean_right_bank_displacement_m)
      ? obj.mean_right_bank_displacement_m
      : null,
    max_bank_displacement_m: isNumber(obj.max_bank_displacement_m)
      ? obj.max_bank_displacement_m
      : null,
    sample_transects: Array.isArray(obj.sample_transects) ? (obj.sample_transects as any[]) : undefined,
  };
}

export function validateRunSummary(data: unknown): RunSummary {
  if (!isObject(data)) {
    throw new Error('Invalid run summary: response root must be an object');
  }
  if (!isString(data.run_id) || !data.run_id.trim()) {
    throw new Error("Invalid run summary: missing or invalid 'run_id'");
  }
  if (!isString(data.status)) {
    throw new Error("Invalid run summary: missing or invalid 'status'");
  }

  // study_aoi
  if (!isObject(data.study_aoi) || !isString(data.study_aoi.wkt)) {
    throw new Error("Invalid run summary: missing or invalid 'study_aoi.wkt'");
  }

  // observations
  if (!isObject(data.observations)) {
    throw new Error("Invalid run summary: missing 'observations' object");
  }
  const baseline = validateObservation(data.observations.baseline, 'baseline (T1)');
  const change = validateObservation(data.observations.change, 'change (T2)');

  // flood transitions
  const flood_transitions_km2 = validateFloodTransitions(data.flood_transitions_km2);

  // riverbank
  const riverbank_dynamics = validateRiverbankDynamics(data.riverbank_dynamics);

  // optional ai_evaluation
  let ai_evaluation = undefined;
  if (isObject(data.ai_evaluation)) {
    const ai = data.ai_evaluation;
    if (
      isString(ai.model_id) &&
      isNumber(ai.sample_evaluated) &&
      isNumber(ai.mean_water_probability) &&
      typeof ai.additivity_verified === 'boolean'
    ) {
      ai_evaluation = {
        model_id: ai.model_id,
        sample_evaluated: ai.sample_evaluated,
        mean_water_probability: ai.mean_water_probability,
        additivity_verified: ai.additivity_verified,
        sample_explanations: Array.isArray(ai.sample_explanations)
          ? (ai.sample_explanations as any[])
          : undefined,
      };
    }
  }

  return {
    run_id: data.run_id,
    status: data.status,
    completed_at: isString(data.completed_at) ? data.completed_at : undefined,
    study_aoi: {
      wkt: data.study_aoi.wkt as string,
      geometric_vector_area_km2: isNumber(data.study_aoi.geometric_vector_area_km2)
        ? data.study_aoi.geometric_vector_area_km2
        : undefined,
      raster_polygon_area_km2: isNumber(data.study_aoi.raster_polygon_area_km2)
        ? data.study_aoi.raster_polygon_area_km2
        : undefined,
      bounding_box_area_km2: isNumber(data.study_aoi.bounding_box_area_km2)
        ? data.study_aoi.bounding_box_area_km2
        : undefined,
      common_valid_domain_km2: isNumber(data.study_aoi.common_valid_domain_km2)
        ? data.study_aoi.common_valid_domain_km2
        : undefined,
    },
    observations: { baseline, change },
    flood_transitions_km2,
    flood_reconciliation: isObject(data.flood_reconciliation)
      ? {
          net_equals_inundation_minus_recession: Boolean(
            data.flood_reconciliation.net_equals_inundation_minus_recession
          ),
          water_t1_pixels: isNumber(data.flood_reconciliation.water_t1_pixels)
            ? data.flood_reconciliation.water_t1_pixels
            : undefined,
          water_t2_pixels: isNumber(data.flood_reconciliation.water_t2_pixels)
            ? data.flood_reconciliation.water_t2_pixels
            : undefined,
          net_change_pixels: isNumber(data.flood_reconciliation.net_change_pixels)
            ? data.flood_reconciliation.net_change_pixels
            : undefined,
        }
      : undefined,
    riverbank_dynamics,
    ai_evaluation,
  };
}

export function validateVisualManifest(data: unknown): VisualManifest {
  if (!isObject(data)) {
    throw new Error('Invalid visual manifest: response root must be an object');
  }
  if (!isString(data.run_id) || !data.run_id.trim()) {
    throw new Error("Invalid visual manifest: missing or invalid 'run_id'");
  }
  if (!isString(data.status)) {
    throw new Error("Invalid visual manifest: missing or invalid 'status'");
  }

  // geographic_bounds
  if (!isObject(data.geographic_bounds) || !Array.isArray(data.geographic_bounds.epsg4326)) {
    throw new Error("Invalid visual manifest: missing 'geographic_bounds.epsg4326'");
  }
  const epsg4326 = data.geographic_bounds.epsg4326;
  if (epsg4326.length !== 4 || !epsg4326.every(isNumber)) {
    throw new Error("Invalid visual manifest: 'epsg4326' must be an array of 4 coordinates [min_lon, min_lat, max_lon, max_lat]");
  }

  // layers
  if (!Array.isArray(data.layers)) {
    throw new Error("Invalid visual manifest: 'layers' must be an array");
  }

  const layers: VisualLayer[] = data.layers.map((layer, idx) => {
    if (!isObject(layer) || !isString(layer.layer_id) || !isString(layer.title) || !isString(layer.type)) {
      throw new Error(`Invalid layer at index ${idx}: layer_id, title, and type must be strings`);
    }

    let legend = undefined;
    if (isObject(layer.legend)) {
      const leg = layer.legend;
      legend = {
        type: leg.type === 'continuous' ? ('continuous' as const) : ('categorical' as const),
        classes: Array.isArray(leg.classes)
          ? leg.classes.map((c: any) => ({
              value: Number(c.value),
              label: String(c.label),
              color: String(c.color),
              area_km2: isNumber(c.area_km2) ? c.area_km2 : null,
            }))
          : undefined,
        min_db: isNumber(leg.min_db) ? leg.min_db : undefined,
        max_db: isNumber(leg.max_db) ? leg.max_db : undefined,
        units: isString(leg.units) ? leg.units : undefined,
        min: isNumber(leg.min) ? leg.min : undefined,
        max: isNumber(leg.max) ? leg.max : undefined,
        decision_threshold: isNumber(leg.decision_threshold) ? leg.decision_threshold : undefined,
        colormap: isString(leg.colormap) ? leg.colormap : undefined,
      };
    }

    return {
      layer_id: layer.layer_id,
      title: layer.title,
      type: layer.type,
      tile_url_template: isString(layer.tile_url_template) ? layer.tile_url_template : null,
      preview_png_url: isString(layer.preview_png_url) ? layer.preview_png_url : undefined,
      download_geotiff_url: isString(layer.download_geotiff_url) ? layer.download_geotiff_url : undefined,
      legend,
    };
  });

  return {
    run_id: data.run_id,
    status: data.status,
    completed_at: isString(data.completed_at) ? data.completed_at : undefined,
    geographic_bounds: {
      epsg4326: [epsg4326[0], epsg4326[1], epsg4326[2], epsg4326[3]],
      epsg32645: Array.isArray(data.geographic_bounds.epsg32645) && data.geographic_bounds.epsg32645.length === 4
        ? (data.geographic_bounds.epsg32645 as [number, number, number, number])
        : undefined,
      center: isObject(data.geographic_bounds.center) && isNumber(data.geographic_bounds.center.lon) && isNumber(data.geographic_bounds.center.lat)
        ? { lon: data.geographic_bounds.center.lon, lat: data.geographic_bounds.center.lat }
        : undefined,
    },
    pixel_spacing_m: Array.isArray(data.pixel_spacing_m) && data.pixel_spacing_m.length === 2
      ? [data.pixel_spacing_m[0], data.pixel_spacing_m[1]]
      : undefined,
    observations: isObject(data.observations) ? data.observations : undefined,
    layers,
    vectors: Array.isArray(data.vectors) ? (data.vectors as any[]) : undefined,
  };
}

export function validateExplanations(data: unknown): ExplanationsResponse {
  if (!isObject(data)) {
    throw new Error('Invalid explanations response: root must be an object');
  }
  if (!isString(data.model_id) || !data.model_id.trim()) {
    throw new Error("Invalid explanations response: missing 'model_id'");
  }
  if (!isNumber(data.sample_evaluated)) {
    throw new Error("Invalid explanations response: 'sample_evaluated' must be a valid number");
  }
  if (!isNumber(data.mean_water_probability)) {
    throw new Error("Invalid explanations response: 'mean_water_probability' must be a valid number");
  }
  if (typeof data.additivity_verified !== 'boolean') {
    throw new Error("Invalid explanations response: 'additivity_verified' must be boolean");
  }
  if (!Array.isArray(data.sample_explanations)) {
    throw new Error("Invalid explanations response: 'sample_explanations' must be an array");
  }

  const sample_explanations: SampleExplanation[] = data.sample_explanations.map((sample, idx) => {
    if (!isObject(sample)) {
      throw new Error(`Sample explanation at index ${idx} is not an object`);
    }
    if (!isNumber(sample.base_value)) {
      throw new Error(`Sample explanation at index ${idx} missing valid 'base_value'`);
    }
    if (!isNumber(sample.prediction_probability)) {
      throw new Error(`Sample explanation at index ${idx} missing valid 'prediction_probability'`);
    }
    if (!isObject(sample.attributions)) {
      throw new Error(`Sample explanation at index ${idx} missing 'attributions' object`);
    }

    const attr = sample.attributions;
    const requiredFeatures = [
      'vv_db',
      'vh_db',
      'vv_minus_vh_db',
      'cross_pol_ratio',
      'texture_vv',
      'texture_vh',
    ];
    for (const feat of requiredFeatures) {
      if (!isNumber(attr[feat])) {
        throw new Error(`Sample explanation at index ${idx} attribution '${feat}' is missing or not a number`);
      }
    }

    if (!isNumber(sample.sum_attributions)) {
      throw new Error(`Sample explanation at index ${idx} missing valid 'sum_attributions'`);
    }
    if (!isNumber(sample.additivity_error)) {
      throw new Error(`Sample explanation at index ${idx} missing valid 'additivity_error'`);
    }

    // Verify mathematical additivity: |f(x) - (base_value + sum_attributions)| < 1e-4
    const mathematicalError = Math.abs(sample.prediction_probability - (sample.base_value + sample.sum_attributions));
    const isAdditive = mathematicalError < 1e-4 && Boolean(sample.is_additive);

    return {
      base_value: sample.base_value,
      prediction_probability: sample.prediction_probability,
      attributions: {
        vv_db: attr.vv_db as number,
        vh_db: attr.vh_db as number,
        vv_minus_vh_db: attr.vv_minus_vh_db as number,
        cross_pol_ratio: attr.cross_pol_ratio as number,
        texture_vv: attr.texture_vv as number,
        texture_vh: attr.texture_vh as number,
      },
      sum_attributions: sample.sum_attributions,
      additivity_error: sample.additivity_error,
      is_additive: isAdditive,
      baseline_mode: isString(sample.baseline_mode) ? sample.baseline_mode : 'ensemble_root',
    };
  });

  return {
    model_id: data.model_id,
    sample_evaluated: data.sample_evaluated,
    mean_water_probability: data.mean_water_probability,
    additivity_verified: data.additivity_verified,
    sample_explanations,
  };
}

