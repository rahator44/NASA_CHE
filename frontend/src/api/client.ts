/**
 * Earth Pulse SAR — Production Typed API Client with AbortSignal & Runtime Validation
 */

import {
  RunSummary,
  VisualManifest,
  ExplanationsResponse,
  CatalogSearchRequest,
  CatalogSearchResponse,
  AnalysisCreateRequest,
  AnalysisJobStatus,
  AnalysisRunRecord,
} from './types';
import {
  validateRunSummary,
  validateVisualManifest,
  validateExplanations,
} from './validation';
import { explanationsBelongToRun } from '../state/analysisSelection';

// Configurable base URL: uses VITE_API_BASE_URL if set, or defaults to relative path for Vite dev proxy
const envBase =
  (typeof import.meta !== 'undefined' && (import.meta as any)?.env?.VITE_API_BASE_URL) ||
  (typeof globalThis !== 'undefined' && (globalThis as any)?.process?.env?.VITE_API_BASE_URL) ||
  '';
export const API_BASE = envBase.replace(/\/$/, '');
export const API_PREFIX = `${API_BASE}/api/v1`;

// Static demo detection (for GitHub Pages or standalone static builds)
export const isStaticDemo =
  (typeof import.meta !== 'undefined' && (import.meta as any)?.env?.VITE_STATIC_DEMO === 'true') ||
  (typeof globalThis !== 'undefined' && (globalThis as any)?.process?.env?.VITE_STATIC_DEMO === 'true');

const appBase =
  (typeof import.meta !== 'undefined' && (import.meta as any)?.env?.BASE_URL) ||
  '/';
const cleanAppBase = appBase.endsWith('/') ? appBase : `${appBase}/`;

export async function fetchRunSummary(runId: string, signal?: AbortSignal): Promise<RunSummary> {
  const url = isStaticDemo
    ? `${cleanAppBase}data/runs/${encodeURIComponent(runId)}/summary.json`
    : `${API_PREFIX}/runs/${encodeURIComponent(runId)}/summary`;

  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Failed to load scientific summary for ${runId} (HTTP ${res.status})`);
  }
  const rawData = await res.json();
  const validated = validateRunSummary(rawData);
  if (validated.run_id !== runId) {
    throw new Error(`Data integrity violation: requested summary for '${runId}' but received '${validated.run_id}'`);
  }
  return validated;
}

export async function fetchVisualManifest(runId: string, signal?: AbortSignal): Promise<VisualManifest> {
  const url = isStaticDemo
    ? `${cleanAppBase}data/runs/${encodeURIComponent(runId)}/visual_manifest.json`
    : `${API_PREFIX}/runs/${encodeURIComponent(runId)}/visual-manifest`;

  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Failed to load visual manifest for ${runId} (HTTP ${res.status})`);
  }
  const rawData = await res.json();
  const validated = validateVisualManifest(rawData);
  if (validated.run_id !== runId) {
    throw new Error(`Data integrity violation: requested manifest for '${runId}' but received '${validated.run_id}'`);
  }
  return validated;
}

export async function fetchRunExplanations(runId: string, signal?: AbortSignal): Promise<ExplanationsResponse> {
  const url = isStaticDemo
    ? `${cleanAppBase}data/runs/${encodeURIComponent(runId)}/explanations.json`
    : `${API_PREFIX}/runs/${encodeURIComponent(runId)}/explanations`;

  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Failed to load explanations for ${runId} (HTTP ${res.status})`);
  }
  const rawData = await res.json();
  if (!explanationsBelongToRun(rawData, runId)) {
    throw new Error(
      `Data integrity violation: explanations for '${runId}' named a different run`
    );
  }
  return validateExplanations(rawData);
}

function isAnalysisRunRecord(value: unknown): value is AnalysisRunRecord {
  if (!value || typeof value !== 'object') return false;
  const row = value as Partial<AnalysisRunRecord>;
  return typeof row.run_id === 'string' && typeof row.status === 'string';
}

/**
 * Completed and in-progress analysis records for a region.
 * Campaign choices are derived from this catalogue, not a fixed list.
 */
export async function fetchRegionAnalysisResults(
  regionId = 'jamuna_sirajganj',
  signal?: AbortSignal
): Promise<AnalysisRunRecord[]> {
  const url = isStaticDemo
    ? `${cleanAppBase}data/regions/${encodeURIComponent(regionId)}/results.json`
    : `${API_PREFIX}/regions/${encodeURIComponent(regionId)}/results`;

  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Failed to load analysis records for ${regionId} (HTTP ${res.status})`);
  }
  const data = await res.json();
  const rows: unknown[] = Array.isArray(data?.results) ? data.results : [];
  return rows.filter(isAnalysisRunRecord).map((row) => ({
    run_id: row.run_id,
    analysis_type: typeof row.analysis_type === 'string' ? row.analysis_type : '',
    region_id: typeof row.region_id === 'string' ? row.region_id : regionId,
    status: row.status,
    executed_at: typeof row.executed_at === 'string' ? row.executed_at : undefined,
    completed_at: typeof row.completed_at === 'string' ? row.completed_at : row.completed_at ?? null,
    parameters: row.parameters && typeof row.parameters === 'object' ? row.parameters : {},
    outputs: row.outputs && typeof row.outputs === 'object' ? row.outputs : {},
    metadata: row.metadata && typeof row.metadata === 'object' ? row.metadata : {},
  }));
}

/**
 * Safely resolves a tile URL template provided by visual_manifest.json against API origin or static demo base.
 * Preserves Leaflet placeholders {z}, {x}, and {y}.
 * Rejects unexpected hosts and external untrusted domains.
 */
export function resolveTileUrl(tileUrlTemplate: string): string {
  if (!tileUrlTemplate || typeof tileUrlTemplate !== 'string') {
    throw new Error('Tile URL template is empty or invalid');
  }

  if (isStaticDemo) {
    const cleanPath = tileUrlTemplate.replace(/^\/?(api\/v1\/|data\/)/, 'data/');
    return `${cleanAppBase}${cleanPath.replace(/^\/+/, '')}`;
  }

  // Handle absolute URLs
  if (/^https?:\/\//i.test(tileUrlTemplate)) {
    let url: URL;
    try {
      url = new URL(tileUrlTemplate);
    } catch {
      throw new Error(`Invalid tile URL template: ${tileUrlTemplate}`);
    }

    const allowedOrigins = new Set<string>();
    if (typeof window !== 'undefined' && window.location?.origin) {
      allowedOrigins.add(window.location.origin);
    }
    if (API_BASE) {
      try {
        const baseOrigin = new URL(API_BASE, typeof window !== 'undefined' ? window.location?.origin : 'http://localhost').origin;
        allowedOrigins.add(baseOrigin);
      } catch {
        // ignore malformed API_BASE
      }
    }

    if (!allowedOrigins.has(url.origin)) {
      throw new Error(`Untrusted external tile URL template rejected: ${url.origin}`);
    }

    if (!url.pathname.includes('/api/v1/runs/')) {
      throw new Error(`Invalid tile URL path: ${url.pathname}`);
    }

    return tileUrlTemplate;
  }

  // Relative path starting with / or api/
  const cleanPath = tileUrlTemplate.startsWith('/') ? tileUrlTemplate : `/${tileUrlTemplate}`;
  if (!cleanPath.startsWith('/api/v1/runs/')) {
    throw new Error(`Invalid relative tile URL path: ${cleanPath}`);
  }
  return `${API_BASE}${cleanPath}`;
}

export function getPreviewUrl(runId: string, assetName: string): string {
  if (isStaticDemo) {
    return `${cleanAppBase}data/runs/${encodeURIComponent(runId)}/previews/${encodeURIComponent(assetName)}`;
  }
  return `${API_PREFIX}/runs/${encodeURIComponent(runId)}/previews/${encodeURIComponent(assetName)}`;
}

/**
 * Queries NASA ASF / Copernicus Sentinel-1 catalog for IW GRD observations matching AOI and date range.
 */
export async function searchSentinel1Catalog(
  req: CatalogSearchRequest,
  signal?: AbortSignal
): Promise<CatalogSearchResponse> {
  if (isStaticDemo) {
    const is2024 = req.start_date.includes('2024');
    if (is2024) {
      return {
        total_scenes: 2,
        scenes: [],
        compatible_pairs_count: 1,
        compatible_pairs: [
          {
            baseline: {
              scene_name: 'S1A_IW_GRDH_1SDV_20240610T115840_20240610T115905_054260_069B78_A4D1',
              platform: 'Sentinel-1A',
              acquisition_time: '2024-06-10T11:58:40Z',
              orbit_direction: 'DESCENDING',
              relative_orbit: 143,
              polarization: 'VV+VH',
              beam_mode: 'IW',
              processing_level: 'GRD_HD',
              aoi_coverage_pct: 100.0,
            },
            change: {
              scene_name: 'S1A_IW_GRDH_1SDV_20240716T115842_20240716T115907_054785_06AD45_C8E9',
              platform: 'Sentinel-1A',
              acquisition_time: '2024-07-16T11:58:42Z',
              orbit_direction: 'DESCENDING',
              relative_orbit: 143,
              polarization: 'VV+VH',
              beam_mode: 'IW',
              processing_level: 'GRD_HD',
              aoi_coverage_pct: 100.0,
            },
            temporal_baseline_days: 36,
            metrics: {
              flight_direction_match: true,
              track_match: true,
              polarization_match: true,
              beam_mode_match: true,
              processing_level_match: true,
              temporal_baseline_days: 36,
              coverage_baseline_pct: 100.0,
              coverage_change_pct: 100.0,
            },
          },
        ],
      };
    }

    return {
      total_scenes: 4,
      scenes: [],
      compatible_pairs_count: 2,
      compatible_pairs: [
        {
          baseline: {
            scene_name: 'S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8',
            platform: 'Sentinel-1A',
            acquisition_time: '2025-01-12T12:05:03Z',
            orbit_direction: 'ASCENDING',
            relative_orbit: 114,
            polarization: 'VV+VH',
            beam_mode: 'IW',
            processing_level: 'GRD_HD',
            aoi_coverage_pct: 100.0,
          },
          change: {
            scene_name: 'S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB',
            platform: 'Sentinel-1A',
            acquisition_time: '2025-01-24T12:05:02Z',
            orbit_direction: 'ASCENDING',
            relative_orbit: 114,
            polarization: 'VV+VH',
            beam_mode: 'IW',
            processing_level: 'GRD_HD',
            aoi_coverage_pct: 100.0,
          },
          temporal_baseline_days: 12,
          metrics: {
            flight_direction_match: true,
            track_match: true,
            polarization_match: true,
            beam_mode_match: true,
            processing_level_match: true,
            temporal_baseline_days: 12,
            coverage_baseline_pct: 100.0,
            coverage_change_pct: 100.0,
          },
        },
        {
          baseline: {
            scene_name: 'S1A_IW_GRDH_1SDV_20250114T235601_20250114T235626_057447_07129E_B55B',
            platform: 'Sentinel-1A',
            acquisition_time: '2025-01-14T23:56:01Z',
            orbit_direction: 'DESCENDING',
            relative_orbit: 150,
            polarization: 'VV+VH',
            beam_mode: 'IW',
            processing_level: 'GRD_HD',
            aoi_coverage_pct: 100.0,
          },
          change: {
            scene_name: 'S1A_IW_GRDH_1SDV_20250126T235601_20250126T235626_057622_071996_9443',
            platform: 'Sentinel-1A',
            acquisition_time: '2025-01-26T23:56:01Z',
            orbit_direction: 'DESCENDING',
            relative_orbit: 150,
            polarization: 'VV+VH',
            beam_mode: 'IW',
            processing_level: 'GRD_HD',
            aoi_coverage_pct: 100.0,
          },
          temporal_baseline_days: 12,
          metrics: {
            flight_direction_match: true,
            track_match: true,
            polarization_match: true,
            beam_mode_match: true,
            processing_level_match: true,
            temporal_baseline_days: 12,
            coverage_baseline_pct: 100.0,
            coverage_change_pct: 100.0,
          },
        },
      ],
    };
  }

  const url = `${API_PREFIX}/catalog/sentinel1/search`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringifyWithFallback(req),
    signal,
  });

  if (!res.ok) {
    let errDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson?.detail) errDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(`Catalogue search failed: ${errDetail}`);
  }

  const data = await res.json();
  return {
    total_scenes: Number(data.total_scenes || 0),
    scenes: Array.isArray(data.scenes) ? data.scenes : [],
    compatible_pairs_count: Number(data.compatible_pairs_count || 0),
    compatible_pairs: Array.isArray(data.compatible_pairs) ? data.compatible_pairs : [],
  };
}

/**
 * Submits dynamic analysis request.
 * In public demo mode, server returns HTTP 403 or client informs user to download local app.
 */
export async function createAnalysisRequest(
  req: AnalysisCreateRequest,
  signal?: AbortSignal
): Promise<{ run_id: string; status: string; is_demo_restricted?: boolean; message?: string }> {
  if (isStaticDemo) {
    return {
      run_id: '',
      status: 'RESTRICTED',
      is_demo_restricted: true,
      message: 'Dynamic satellite ingestion and ESA SNAP execution require local processing with your own NASA Earthdata credentials. Download Earth Pulse v1.0.0 from GitHub to run on your own machine.',
    };
  }

  const url = `${API_PREFIX}/analysis-requests`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringifyWithFallback(req),
    signal,
  });

  if (res.status === 403) {
    let detail = 'Analysis execution is restricted in public demo mode to protect host compute.';
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    return {
      run_id: '',
      status: 'RESTRICTED',
      is_demo_restricted: true,
      message: detail,
    };
  }

  if (!res.ok) {
    let errDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson?.detail) errDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(`Analysis submission failed: ${errDetail}`);
  }

  return await res.json();
}

/**
 * Polls status of a dynamic analysis job.
 */
export async function getAnalysisJobStatus(
  runId: string,
  signal?: AbortSignal
): Promise<AnalysisJobStatus> {
  const url = `${API_PREFIX}/analysis-requests/${encodeURIComponent(runId)}`;
  const res = await fetch(url, { signal });

  if (!res.ok) {
    throw new Error(`Failed to check job status for ${runId} (HTTP ${res.status})`);
  }

  return await res.json();
}

/**
 * Requests cancellation of an in-flight analysis job.
 */
export async function cancelAnalysisJob(
  runId: string,
  signal?: AbortSignal
): Promise<{ run_id: string; status: string }> {
  const url = `${API_PREFIX}/analysis-requests/${encodeURIComponent(runId)}/cancel`;
  const res = await fetch(url, {
    method: 'POST',
    signal,
  });

  if (!res.ok) {
    throw new Error(`Failed to cancel job ${runId} (HTTP ${res.status})`);
  }

  return await res.json();
}

function jsonStringifyWithFallback(obj: unknown): string {
  return JSON.stringify(obj, (_, val) => (typeof val === 'number' && !isFinite(val) ? null : val));
}
