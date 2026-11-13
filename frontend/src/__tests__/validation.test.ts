import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  validateRunSummary,
  validateVisualManifest,
  validateExplanations,
} from '../api/validation';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const RUN_2025_LOCAL = path.join(REPO_ROOT, 'data/runs/run_20261111_164348_f3c2b8');
const RUN_2025_PUBLIC = path.join(process.cwd(), 'public/data/runs/run_20261111_164348_f3c2b8');
const RUN_2025_DIR = fs.existsSync(RUN_2025_LOCAL) ? RUN_2025_LOCAL : RUN_2025_PUBLIC;

const RUN_2024_LOCAL = path.join(REPO_ROOT, 'data/runs/run_20261110_221732_1f2e94');
const RUN_2024_PUBLIC = path.join(process.cwd(), 'public/data/runs/run_20261110_221732_1f2e94');
const RUN_2024_DIR = fs.existsSync(RUN_2024_LOCAL) ? RUN_2024_LOCAL : RUN_2024_PUBLIC;

describe('Scientific Contract Validation Suite', () => {
  it('should validate real 2025 run summary and confirm exact scientific invariants', () => {
    const raw = JSON.parse(fs.readFileSync(path.join(RUN_2025_DIR, 'summary.json'), 'utf-8'));
    const validated = validateRunSummary(raw);

    assert.equal(validated.run_id, 'run_20261111_164348_f3c2b8');
    assert.equal(validated.status, 'COMPLETED');

    // Net Candidate Water Change Invariant: +1.0440 km²
    const net = validated.flood_transitions_km2.net_candidate_water_change;
    assert.equal(Math.round(net * 10000) / 10000, 1.0440);
    assert.equal(validated.flood_transitions_km2.newly_inundated, 1.6160);
    assert.equal(Math.round(validated.flood_transitions_km2.receded_water * 10000) / 10000, 0.5720);
    assert.equal(validated.flood_transitions_km2.persistent_water, 11.4132);
    assert.equal(validated.flood_transitions_km2.indeterminate_floor, 2.2296);

    // Observations
    assert.equal(validated.observations.baseline.scene_name, 'S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8');
    assert.equal(validated.observations.baseline.acquisition_time, '2025-01-12T12:05:03Z');
    assert.ok(validated.observations.baseline.threshold_vv_db < -10);
    assert.ok(validated.observations.baseline.threshold_vh_db < -15);

    // Riverbank 2025 Quality Gate
    assert.equal(validated.riverbank_dynamics.evaluated_transects, 36);
    assert.equal(validated.riverbank_dynamics.valid_migration_transects, 35);
    assert.equal(validated.riverbank_dynamics.unqualified_transects_count, 1);
    assert.ok(Array.isArray(validated.riverbank_dynamics.unqualified_transects));
    assert.equal(validated.riverbank_dynamics.unqualified_transects[0].transect_row, 396);

    // AI Evaluation
    assert.ok(validated.ai_evaluation);
    assert.equal(validated.ai_evaluation.model_id, 'phase7a_rf_jamuna_v1');
    assert.equal(validated.ai_evaluation.sample_evaluated, 100);
    assert.equal(validated.ai_evaluation.additivity_verified, true);
    assert.ok(!Number.isNaN(validated.ai_evaluation.mean_water_probability));
  });

  it('should validate real 2024 run summary and handle nullable quality-gate fields', () => {
    const raw = JSON.parse(fs.readFileSync(path.join(RUN_2024_DIR, 'summary.json'), 'utf-8'));
    const validated = validateRunSummary(raw);

    assert.equal(validated.run_id, 'run_20261110_221732_1f2e94');
    assert.equal(validated.status, 'COMPLETED');

    // 2024 Net Change Invariant: +5.8432 km²
    const net = validated.flood_transitions_km2.net_candidate_water_change;
    assert.equal(Math.round(net * 10000) / 10000, 5.8432);

    // Riverbank 2024 (legacy baseline: unqualified_transects_count is unrecorded/undefined)
    assert.equal(validated.riverbank_dynamics.evaluated_transects, 36);
    assert.equal(validated.riverbank_dynamics.valid_migration_transects, 36);
    assert.equal(validated.riverbank_dynamics.unqualified_transects_count, undefined);
  });

  it('should reject malformed summary data with descriptive errors', () => {
    // Missing required flood field
    assert.throws(() => {
      validateRunSummary({
        run_id: 'test_run',
        status: 'COMPLETED',
        study_aoi: { wkt: 'POLYGON((0 0, 1 1, 0 1, 0 0))' },
        observations: {
          baseline: { scene_name: 's1', acquisition_time: 't1', water_area_km2: 1, threshold_vv_db: -12, threshold_vh_db: -20 },
          change: { scene_name: 's2', acquisition_time: 't2', water_area_km2: 2, threshold_vv_db: -12, threshold_vh_db: -20 },
        },
        flood_transitions_km2: {
          persistent_water: 10,
          // missing newly_inundated
          receded_water: 1,
          persistent_non_water: 50,
          indeterminate_floor: 2,
          net_candidate_water_change: 9,
        },
        riverbank_dynamics: { evaluated_transects: 36, valid_migration_transects: 36 },
      });
    }, /required field 'newly_inundated' is missing/);
  });

  it('should validate real 2025 and 2024 visual manifests', () => {
    for (const runDir of [RUN_2025_DIR, RUN_2024_DIR]) {
      const raw = JSON.parse(fs.readFileSync(path.join(runDir, 'visual_manifest.json'), 'utf-8'));
      const manifest = validateVisualManifest(raw);

      assert.ok(manifest.layers.length >= 6);
      const epsg4326 = manifest.geographic_bounds.epsg4326;
      assert.equal(epsg4326.length, 4);
      assert.ok(epsg4326[0] < epsg4326[2]); // min_lon < max_lon
      assert.ok(epsg4326[1] < epsg4326[3]); // min_lat < max_lat

      // Check transitions layer legend has classes
      const transLayer = manifest.layers.find((l) => l.layer_id === 'transitions');
      assert.ok(transLayer);
      assert.ok(transLayer.legend?.classes);
      assert.ok(transLayer.legend.classes.length >= 5);

      // In 2025, class 6 is Outside AOI / NoData transparent
      if (runDir.includes('2025')) {
        assert.equal(transLayer.legend.classes.length, 6);
        const class6 = transLayer.legend.classes.find((c) => c.value === 6);
        assert.ok(class6);
        assert.equal(class6.label, 'Outside AOI / NoData');
        assert.equal(class6.color, '#00000000');
      }

      // Check rf_probability layer
      const rfLayer = manifest.layers.find((l) => l.layer_id === 'rf_probability');
      assert.ok(rfLayer);
      assert.equal(rfLayer.legend?.decision_threshold, 0.35);
    }
  });

  it('should validate real Saabas explanations and confirm tree additivity', () => {
    for (const runDir of [RUN_2025_DIR, RUN_2024_DIR]) {
      const raw = JSON.parse(fs.readFileSync(path.join(runDir, 'explanations.json'), 'utf-8'));
      const xai = validateExplanations(raw);

      assert.equal(xai.model_id, 'phase7a_rf_jamuna_v1');
      assert.equal(xai.sample_explanations.length, 5);
      assert.equal(xai.additivity_verified, true);

      for (const sample of xai.sample_explanations) {
        // Confirm all 6 features are present
        const attributions = sample.attributions;
        assert.ok(typeof attributions.vv_db === 'number');
        assert.ok(typeof attributions.vh_db === 'number');
        assert.ok(typeof attributions.vv_minus_vh_db === 'number');
        assert.ok(typeof attributions.cross_pol_ratio === 'number');
        assert.ok(typeof attributions.texture_vv === 'number');
        assert.ok(typeof attributions.texture_vh === 'number');

        // Confirm mathematical additivity: Prediction ≈ Base value + sum(attributions)
        const expectedPred = sample.base_value + sample.sum_attributions;
        const diff = Math.abs(sample.prediction_probability - expectedPred);
        assert.ok(diff < 1e-6, `Additivity violated: diff ${diff} exceeds tolerance`);
        assert.equal(sample.is_additive, true);
      }
    }
  });

  it('should reject non-finite numbers (NaN, Infinity, -Infinity)', () => {
    // NaN in water_area_km2
    assert.throws(() => {
      validateRunSummary({
        run_id: 'test_run',
        status: 'COMPLETED',
        study_aoi: { wkt: 'POLYGON((0 0, 1 1, 0 1, 0 0))' },
        observations: {
          baseline: { scene_name: 's1', acquisition_time: 't1', water_area_km2: NaN, threshold_vv_db: -12, threshold_vh_db: -20 },
          change: { scene_name: 's2', acquisition_time: 't2', water_area_km2: 2, threshold_vv_db: -12, threshold_vh_db: -20 },
        },
        flood_transitions_km2: {
          persistent_water: 10,
          newly_inundated: 1,
          receded_water: 1,
          persistent_non_water: 50,
          indeterminate_floor: 2,
          net_candidate_water_change: 9,
        },
        riverbank_dynamics: { evaluated_transects: 36, valid_migration_transects: 36 },
      });
    }, /water_area_km2 must be a valid number/);

    // Infinity in flood_transitions
    assert.throws(() => {
      validateRunSummary({
        run_id: 'test_run',
        status: 'COMPLETED',
        study_aoi: { wkt: 'POLYGON((0 0, 1 1, 0 1, 0 0))' },
        observations: {
          baseline: { scene_name: 's1', acquisition_time: 't1', water_area_km2: 10, threshold_vv_db: -12, threshold_vh_db: -20 },
          change: { scene_name: 's2', acquisition_time: 't2', water_area_km2: 2, threshold_vv_db: -12, threshold_vh_db: -20 },
        },
        flood_transitions_km2: {
          persistent_water: Infinity,
          newly_inundated: 1,
          receded_water: 1,
          persistent_non_water: 50,
          indeterminate_floor: 2,
          net_candidate_water_change: 9,
        },
        riverbank_dynamics: { evaluated_transects: 36, valid_migration_transects: 36 },
      });
    }, /field 'persistent_water' is missing or not a valid number/);
  });

  it('should enforce Saabas additivity and reject non-finite attributions', () => {
    // Missing sum_attributions
    assert.throws(() => {
      validateExplanations({
        model_id: 'test_model',
        sample_evaluated: 1,
        mean_water_probability: 0.5,
        additivity_verified: true,
        sample_explanations: [
          {
            base_value: 0.4,
            prediction_probability: 0.7,
            attributions: {
              vv_db: 0.1,
              vh_db: 0.1,
              vv_minus_vh_db: 0.05,
              cross_pol_ratio: 0.05,
              texture_vv: 0.0,
              texture_vh: 0.0,
            },
            // missing sum_attributions
            additivity_error: 0.0,
            is_additive: true,
          },
        ],
      });
    }, /missing valid 'sum_attributions'/);

    // Violating additivity (> 1e-4) should result in is_additive = false
    const validated = validateExplanations({
      model_id: 'test_model',
      sample_evaluated: 1,
      mean_water_probability: 0.5,
      additivity_verified: true,
      sample_explanations: [
        {
          base_value: 0.4,
          prediction_probability: 0.9, // discrepancy: 0.4 + 0.3 = 0.7 != 0.9
          attributions: {
            vv_db: 0.1,
            vh_db: 0.1,
            vv_minus_vh_db: 0.05,
            cross_pol_ratio: 0.05,
            texture_vv: 0.0,
            texture_vh: 0.0,
          },
          sum_attributions: 0.3,
          additivity_error: 0.2,
          is_additive: true,
        },
      ],
    });
    assert.equal(validated.sample_explanations[0].is_additive, false);
  });
});
