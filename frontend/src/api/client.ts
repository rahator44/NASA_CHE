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

export async function fetchRunSummary(runId: string, signal?: AbortSignal): Promise<RunSummary> {
  const url = `${API_PREFIX}/runs/${encodeURIComponent(runId)}/summary`;
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
  const url = `${API_PREFIX}/runs/${encodeURIComponent(runId)}/visual-manifest`;
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
  const url = `${API_PREFIX}/runs/${encodeURIComponent(runId)}/explanations`;
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
  const url = `${API_PREFIX}/regions/${encodeURIComponent(regionId)}/results`;
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
 * Safely resolves a tile URL template provided by visual_manifest.json against API origin.
 * Preserves Leaflet placeholders {z}, {x}, and {y}.
 * Rejects unexpected hosts and external untrusted domains.
 */
export function resolveTileUrl(tileUrlTemplate: string): string {
  if (!tileUrlTemplate || typeof tileUrlTemplate !== 'string') {
    throw new Error('Tile URL template is empty or invalid');
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
  return `${API_PREFIX}/runs/${encodeURIComponent(runId)}/previews/${encodeURIComponent(assetName)}`;
}


/**
 * Queries NASA ASF / Copernicus Sentinel-1 catalog for IW GRD observations matching AOI and date range.
 */
export async function searchSentinel1Catalog(
  req: CatalogSearchRequest,
  signal?: AbortSignal
): Promise<CatalogSearchResponse> {
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
 * In public demo mode, server returns HTTP 403 to protect host compute.
 */
export async function createAnalysisRequest(
  req: AnalysisCreateRequest,
  signal?: AbortSignal
): Promise<{ run_id: string; status: string; is_demo_restricted?: boolean; message?: string }> {
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
