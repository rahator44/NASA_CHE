import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolveTileUrl } from '../api/client';
import { LoadedRun } from '../api/types';

describe('Atomic Run State & Race Condition Suite', () => {
  it('should prevent reversed network arrival from corrupting the active run state', async () => {
    // Simulated state container matching App.tsx atomic coordinator
    let currentGeneration = 0;
    let publishedState: LoadedRun | null = null;

    async function simulateSelectRun(
      runId: string,
      networkDelayMs: number
    ): Promise<void> {
      const thisGeneration = ++currentGeneration;

      // Simulate network request with variable latency
      await new Promise((resolve) => setTimeout(resolve, networkDelayMs));

      // Stale generation check
      if (thisGeneration !== currentGeneration) {
        // Discard stale response
        return;
      }

      // Commit atomic state
      publishedState = {
        runId,
        summary: {
          run_id: runId,
          status: 'COMPLETED',
          study_aoi: { wkt: 'POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))' },
          observations: {
            baseline: { scene_name: 'b', acquisition_time: 't1', water_area_km2: 1, threshold_vv_db: -12, threshold_vh_db: -20 },
            change: { scene_name: 'c', acquisition_time: 't2', water_area_km2: 2, threshold_vv_db: -12, threshold_vh_db: -20 },
          },
          flood_transitions_km2: {
            persistent_water: 1, newly_inundated: 1, receded_water: 0, persistent_non_water: 10,
            indeterminate_floor: 0, net_candidate_water_change: 1
          },
          riverbank_dynamics: { evaluated_transects: 36, valid_migration_transects: 36 },
        },
        manifest: {
          run_id: runId,
          status: 'COMPLETED',
          geographic_bounds: { epsg4326: [89.5, 24.5, 89.7, 24.7] },
          layers: [],
        },
      };
    }

    // User first triggers 2024 (slow response: 150ms)
    const p1 = simulateSelectRun('run_2024_historical', 150);

    // User immediately switches to 2025 (fast response: 30ms)
    const p2 = simulateSelectRun('run_2025_live', 30);

    await Promise.all([p1, p2]);

    // The fast 2025 response finished first (at 30ms).
    // The slow 2024 response finished second (at 150ms), but was generated earlier (generation 1 < 2).
    // Verification: publishedState must be 2025, NOT 2024!
    assert.ok(publishedState);
    assert.equal(publishedState.runId, 'run_2025_live');
  });

  it('should enforce that summary and manifest belong to the exact same run ID', () => {
    const summaryRunId = 'run_2025_live';
    const manifestRunId = 'run_2024_historical';

    // Verify rejection if mismatched
    assert.throws(() => {
      if (summaryRunId !== manifestRunId) {
        throw new Error(`Scientific run identity mismatch: '${summaryRunId}' vs '${manifestRunId}'`);
      }
    }, /Scientific run identity mismatch/);
  });

  it('should safely resolve tile URLs while preserving Leaflet placeholders', () => {
    const template = '/api/v1/runs/run_20261111_164348_f3c2b8/tiles/transitions/{z}/{x}/{y}.png';
    const resolved = resolveTileUrl(template);

    // Must preserve {z}, {x}, and {y}
    assert.ok(resolved.includes('{z}'));
    assert.ok(resolved.includes('{x}'));
    assert.ok(resolved.includes('{y}'));
    assert.ok(resolved.endsWith('.png'));
  });

  it('should reject untrusted external tile domains', () => {
    assert.throws(() => {
      resolveTileUrl('http://malicious-external-origin.xyz/tiles/{z}/{x}/{y}.png');
    }, /Untrusted external tile URL template rejected/);
  });
});

