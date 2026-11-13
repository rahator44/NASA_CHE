/**
 * Shared analysis identity.
 * The selected analysis is the `run` query parameter. Pages read that id;
 * they do not keep a second campaign choice.
 */

import { AnalysisRunRecord, CampaignOption, LoadedRun } from '../api/types';

export const DEFAULT_ANALYSIS_ID = 'run_20261111_164348_f3c2b8';

/** Seeded Jamuna campaigns. Labels only — metrics come from each record. */
export const ARCHIVED_CAMPAIGNS: Record<string, { label: string; dateRange: string }> = {
  run_20261111_164348_f3c2b8: {
    label: 'Archived · January 2025 Jamuna observation',
    dateRange: '2025-01-12 → 2025-01-24',
  },
  run_20261110_221732_1f2e94: {
    label: 'Archived · Summer 2024 Jamuna monsoon baseline',
    dateRange: '2024-06-10 → 2024-07-16',
  },
};

const ARCHIVED_ORDER = Object.keys(ARCHIVED_CAMPAIGNS);

export function resolveSelectedAnalysisId(search: string, fallback = DEFAULT_ANALYSIS_ID): string {
  const params = new URLSearchParams(search.startsWith('?') || search === '' ? search : `?${search}`);
  const run = params.get('run')?.trim();
  return run ? run : fallback;
}

/**
 * Carry the current analysis id onto in-app navigations unless the destination
 * already names a run (completed-job links set `?run=` explicitly).
 */
export function mergeNavigationTarget(to: string, currentSearch: string): string {
  const hashIndex = to.indexOf('#');
  const hash = hashIndex >= 0 ? to.slice(hashIndex) : '';
  const withoutHash = hashIndex >= 0 ? to.slice(0, hashIndex) : to;
  const url = new URL(withoutHash || '/', 'http://earthpulse.local');
  if (!url.searchParams.has('run')) {
    const run = resolveSelectedAnalysisId(currentSearch, '');
    if (run) url.searchParams.set('run', run);
  }
  const query = url.searchParams.toString();
  return `${url.pathname}${query ? `?${query}` : ''}${hash}`;
}

export function assertPublishedRunIdentity(
  requestedId: string,
  summaryRunId: string,
  manifestRunId: string
): void {
  if (summaryRunId !== requestedId || manifestRunId !== requestedId) {
    throw new Error(
      `Scientific run identity mismatch: requested '${requestedId}', received summary '${summaryRunId}' and manifest '${manifestRunId}'`
    );
  }
}

/** Explanations are optional. A payload that names a different run is discarded. */
export function explanationsBelongToRun(payload: unknown, runId: string): boolean {
  if (!payload || typeof payload !== 'object') return false;
  const named = (payload as { run_id?: unknown }).run_id;
  if (typeof named === 'string' && named !== runId) return false;
  return true;
}

export function recordHasViewableOutputs(record: AnalysisRunRecord): boolean {
  if (record.status !== 'COMPLETED') return false;
  const outputs = record.outputs || {};
  return Boolean(outputs.summary || outputs.visual_manifest);
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function datesFromRecord(record: AnalysisRunRecord): string {
  const params = record.parameters || {};
  const start = typeof params.start_date === 'string' ? params.start_date : '';
  const end = typeof params.end_date === 'string' ? params.end_date : '';
  if (start && end) return `${start} → ${end}`;
  const acquisitions = params.satellite_acquisitions;
  if (Array.isArray(acquisitions) && acquisitions.length >= 2) {
    const first = acquisitions[0];
    const last = acquisitions[acquisitions.length - 1];
    if (typeof first === 'string' && typeof last === 'string') return `${first} → ${last}`;
  }
  return 'Dates unavailable';
}

export function campaignOptionFromRecord(record: AnalysisRunRecord): CampaignOption {
  const archived = ARCHIVED_CAMPAIGNS[record.run_id];
  const dateRange = datesFromRecord(record);
  const resolvedDates = dateRange === 'Dates unavailable' && archived ? archived.dateRange : dateRange;
  return {
    id: record.run_id,
    label: archived ? archived.label : `Completed analysis · ${resolvedDates}`,
    dateRange: archived ? archived.dateRange : resolvedDates,
    archived: Boolean(archived),
    description: archived
      ? 'Archived Jamuna demonstration. Figures belong only to this run.'
      : 'Completed analysis. Figures are read from this run only.',
    netChangeKm2: finiteNumber(record.metadata?.net_candidate_water_change_km2),
    status: record.status,
  };
}

export function buildCampaignOptions(records: AnalysisRunRecord[]): CampaignOption[] {
  const options = records.filter(recordHasViewableOutputs).map(campaignOptionFromRecord);
  const archived: CampaignOption[] = [];
  const completed: CampaignOption[] = [];
  for (const option of options) {
    if (option.archived) archived.push(option);
    else completed.push(option);
  }
  archived.sort((a, b) => ARCHIVED_ORDER.indexOf(a.id) - ARCHIVED_ORDER.indexOf(b.id));
  return [...archived, ...completed];
}

export function optionFromLoadedRun(run: LoadedRun): CampaignOption {
  const archived = ARCHIVED_CAMPAIGNS[run.runId];
  const start = run.summary.observations?.baseline?.acquisition_time?.slice(0, 10) || '';
  const end = run.summary.observations?.change?.acquisition_time?.slice(0, 10) || '';
  const dateRange = start && end ? `${start} → ${end}` : archived?.dateRange || 'Dates unavailable';
  const net = finiteNumber(run.summary.flood_transitions_km2?.net_candidate_water_change);
  return {
    id: run.runId,
    label: archived ? archived.label : `Completed analysis · ${dateRange}`,
    dateRange: archived ? archived.dateRange : dateRange,
    archived: Boolean(archived),
    description: 'Published outputs were loaded for this analysis.',
    netChangeKm2: net,
    status: 'COMPLETED',
  };
}

/**
 * Catalogue options, plus the loaded run when the catalogue has not caught up,
 * plus an explicit unavailable row when the requested id has no outputs.
 * Does not invent a completed analysis.
 */
export function mergeDisplayedCampaigns(
  catalogue: CampaignOption[],
  selectedId: string,
  loaded: LoadedRun | null
): CampaignOption[] {
  const options = [...catalogue];
  const known = new Set(options.map((option) => option.id));
  if (loaded && loaded.runId === selectedId && loaded.summary.run_id === selectedId && !known.has(selectedId)) {
    options.push(optionFromLoadedRun(loaded));
    known.add(selectedId);
  }
  if (selectedId && !known.has(selectedId)) {
    options.push({
      id: selectedId,
      label: `Requested analysis · ${selectedId}`,
      dateRange: 'Not in the analysis catalogue',
      archived: false,
      description: 'This id has no published analysis record.',
      netChangeKm2: null,
      status: 'UNKNOWN',
      unavailable: true,
    });
  }
  return options;
}
