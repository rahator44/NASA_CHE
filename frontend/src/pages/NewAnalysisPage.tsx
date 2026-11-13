import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AoiDrawingMap } from '../components/Map/AoiDrawingMap';
import {
  searchSentinel1Catalog,
  createAnalysisRequest,
  getAnalysisJobStatus,
  cancelAnalysisJob,
} from '../api/client';
import { ARCHIVED_CAMPAIGNS } from '../state/analysisSelection';
import {
  CatalogSearchResponse,
  CompatiblePair,
  GeometryValidationResult,
  AnalysisJobStatus,
} from '../api/types';
import {
  DEMO_STUDY_AOI_WKT,
  validateAoiGeometry,
  parseWktPolygon,
} from '../utils/wkt';
import { Link, useRouter } from '../router/Router';

export const NewAnalysisPage: React.FC = () => {
  const { navigate } = useRouter();

  // AOI State (initializes to verified Jamuna demonstration AOI)
  const [aoiWkt, setAoiWkt] = useState<string>(DEMO_STUDY_AOI_WKT);
  const [aoiValidation, setAoiValidation] = useState<GeometryValidationResult>(() =>
    validateAoiGeometry(parseWktPolygon(DEMO_STUDY_AOI_WKT))
  );

  // Date Selection State
  const [startDate, setStartDate] = useState<string>('2024-06-01');
  const [endDate, setEndDate] = useState<string>('2024-07-31');
  const [dateError, setDateError] = useState<string | null>(null);

  // Catalogue Search State
  const [isSearchingCatalog, setIsSearchingCatalog] = useState<boolean>(false);
  const [catalogResponse, setCatalogResponse] = useState<CatalogSearchResponse | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedPairIndex, setSelectedPairIndex] = useState<number>(0);

  // Dynamic Analysis Execution State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [activeJob, setActiveJob] = useState<AnalysisJobStatus | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [demoRestrictedNotice, setDemoRestrictedNotice] = useState<string | null>(null);

  // Polling ref for background analysis status
  const pollTimerRef = useRef<number | null>(null);

  // Validate dates
  useEffect(() => {
    if (!startDate || !endDate) {
      setDateError('Both start date and end date are required.');
      return;
    }
    if (startDate > endDate) {
      setDateError(`Start date (${startDate}) cannot be after end date (${endDate}).`);
      return;
    }
    const currentYear = new Date().getUTCFullYear();
    const startYear = parseInt(startDate.split('-')[0], 10);
    if (startYear > currentYear) {
      setDateError(`Start year (${startYear}) cannot be in the future. SAR observations exist up to present.`);
      return;
    }
    setDateError(null);
  }, [startDate, endDate]);

  const handleAoiChange = useCallback((wkt: string, val: GeometryValidationResult) => {
    setAoiWkt(wkt);
    setAoiValidation(val);
    // Invalidate stale catalog results when AOI changes
    setCatalogResponse(null);
    setCatalogError(null);
  }, []);

  // Quick Date Preset Selectors
  const applyPreset = (preset: '2024_monsoon' | '2025_january') => {
    if (preset === '2024_monsoon') {
      setStartDate('2024-06-01');
      setEndDate('2024-07-31');
    } else {
      setStartDate('2025-01-01');
      setEndDate('2025-01-31');
    }
    setCatalogResponse(null);
    setCatalogError(null);
  };

  // Perform Real Sentinel-1 Catalogue Search
  const handleSearchCatalog = async () => {
    if (!aoiValidation.isValid) {
      setCatalogError('Cannot search catalog: Please select a valid Jamuna River study area first.');
      return;
    }
    if (dateError) {
      setCatalogError(dateError);
      return;
    }

    setIsSearchingCatalog(true);
    setCatalogError(null);
    setCatalogResponse(null);

    try {
      const resp = await searchSentinel1Catalog({
        aoi_wkt: aoiWkt,
        start_date: startDate,
        end_date: endDate,
        max_results: 50,
      });

      setCatalogResponse(resp);
      setSelectedPairIndex(0);
      if (resp.total_scenes === 0) {
        setCatalogError(
          `No Sentinel-1 IW GRD observations found intersecting the selected AOI between ${startDate} and ${endDate}. Consider widening the date window to match the 12-day orbital repeat cycle.`
        );
      }
    } catch (err) {
      setCatalogError(err instanceof Error ? err.message : 'Satellite catalogue query failed.');
    } finally {
      setIsSearchingCatalog(false);
    }
  };

  // Submit Dynamic Analysis Job
  const handleStartAnalysis = async () => {
    if (!aoiValidation.isValid || dateError) return;

    setIsSubmitting(true);
    setSubmissionError(null);
    setDemoRestrictedNotice(null);

    // If a compatible pair was selected from catalog, use its exact observation timestamps
    const selectedPair: CompatiblePair | undefined =
      catalogResponse?.compatible_pairs?.[selectedPairIndex];

    const pairStartDate = selectedPair
      ? selectedPair.baseline.acquisition_time.slice(0, 10)
      : startDate;
    const pairEndDate = selectedPair
      ? selectedPair.change.acquisition_time.slice(0, 10)
      : endDate;

    try {
      const res = await createAnalysisRequest({
        aoi_wkt: aoiWkt,
        start_date: pairStartDate,
        end_date: pairEndDate,
        mode: 'two_date_comparison',
        parameters: selectedPair
          ? {
              baseline_scene: selectedPair.baseline.scene_name,
              change_scene: selectedPair.change.scene_name,
              temporal_baseline_days: selectedPair.temporal_baseline_days,
            }
          : {},
      });

      if (res.is_demo_restricted) {
        setDemoRestrictedNotice(
          res.message ||
            'Job execution is protected in Public Demo Mode to preserve server compute resources.'
        );
        setIsSubmitting(false);
        return;
      }

      // Initial job state
      setActiveJob({
        run_id: res.run_id,
        status: (res.status as any) || 'CREATED',
        progress_pct: 0,
        stage: 'INITIALIZING',
      });

      // Start status polling
      startPolling(res.run_id);
    } catch (err) {
      setSubmissionError(err instanceof Error ? err.message : 'Failed to submit analysis request.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Poll Analysis Status
  const startPolling = (runId: string) => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
    }

    pollTimerRef.current = window.setInterval(async () => {
      try {
        const status = await getAnalysisJobStatus(runId);
        setActiveJob(status);

        if (status.status === 'COMPLETED' || status.status === 'FAILED' || status.status === 'CANCELLED') {
          if (pollTimerRef.current) {
            window.clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
        }
      } catch (err) {
        console.warn(`Polling check for ${runId} encountered:`, err);
      }
    }, 2500);
  };

  // Cancel in-flight job
  const handleCancelJob = async () => {
    if (!activeJob) return;
    try {
      await cancelAnalysisJob(activeJob.run_id);
      setActiveJob((prev) => (prev ? { ...prev, status: 'CANCELLED', stage: 'CANCELLED' } : null));
      if (pollTimerRef.current) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    } catch (err) {
      console.error('Cancellation failed:', err);
    }
  };

  // Cleanup polling timer on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        window.clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  const selectedPair = catalogResponse?.compatible_pairs?.[selectedPairIndex];

  return (
    <div className="new-analysis-page">
      {/* Top Header Banner */}
      <div className="new-analysis-header">
        <div className="header-info">
          <div className="badge-row">
            <span className="badge badge-cyan">NASA ASF / Sentinel-1 DAAC</span>
            <span className="badge badge-purple">Interactive WebGIS</span>
            <span className="badge badge-outline">Braided Jamuna Corridor</span>
          </div>
          <h1 className="page-title">New Satellite Analysis</h1>
          <p className="page-subtitle">
            Select an area and observation dates to explore available Sentinel-1 radar imagery.
          </p>
        </div>

        <div className="header-actions">
          <Link to="/explorer" className="btn btn-secondary">
            🗺️ View Current Campaign
          </Link>
        </div>
      </div>

      {/* Main Analysis Workspace */}
      <div className="new-analysis-workspace">
        {/* Left Column: Interactive Map & Area Drawing */}
        <div className="analysis-map-column">
          <AoiDrawingMap
            aoiWkt={aoiWkt}
            onAoiChange={handleAoiChange}
            validation={aoiValidation}
          />
        </div>

        {/* Right Column: Workflow Steps & Controls */}
        <div className="analysis-controls-column">
          <div className="controls-scroll-wrapper">
            {/* STEP 1: Area of Interest Confirmation */}
            <div className="workflow-card">
              <div className="step-badge-row">
                <span className="step-num">Step 1</span>
                <span className="step-label">Area of Interest (AOI)</span>
              </div>
              <h3 className="card-title">Geographic Study Area</h3>

              <div className="aoi-summary-box">
                <div className="summary-stat-row">
                  <span className="stat-label">Calculated Area:</span>
                  <span className="stat-val highlight">
                    {aoiValidation.areaKm2 > 0 ? `${aoiValidation.areaKm2.toFixed(2)} km²` : 'None Selected'}
                  </span>
                </div>
                <div className="summary-stat-row">
                  <span className="stat-label">Metric Equivalence:</span>
                  <span className="stat-val">
                    {aoiValidation.areaKm2 > 0 ? `${(aoiValidation.areaKm2 * 100).toFixed(0)} hectares` : '—'}
                  </span>
                </div>
                <div className="summary-stat-row">
                  <span className="stat-label">Corridor Status:</span>
                  <span className={`status-pill ${aoiValidation.isContainedInStudyRegion ? 'contained' : 'disjoint'}`}>
                    {aoiValidation.isContainedInStudyRegion ? '✓ Jamuna Reach Verified' : '⚠️ Outside Corridor'}
                  </span>
                </div>
              </div>

              {aoiValidation.error && (
                <div className="alert-box alert-warning">
                  <span>⚠️ {aoiValidation.error}</span>
                </div>
              )}
            </div>

            {/* STEP 2: Observation Window & Date Selection */}
            <div className="workflow-card">
              <div className="step-badge-row">
                <span className="step-num">Step 2</span>
                <span className="step-label">Temporal Window</span>
              </div>
              <h3 className="card-title">Observation Date Range</h3>

              {/* Preset buttons */}
              <div className="date-presets-bar">
                <span className="presets-label">Presets:</span>
                <button
                  type="button"
                  className="btn-preset"
                  onClick={() => applyPreset('2024_monsoon')}
                  title="Monsoon flood baseline (June–July 2024)"
                >
                  Summer 2024 Monsoon
                </button>
                <button
                  type="button"
                  className="btn-preset"
                  onClick={() => applyPreset('2025_january')}
                  title="Dry season live acquisition (January 2025)"
                >
                  January 2025 Live
                </button>
              </div>

              {/* Date Inputs */}
              <div className="date-inputs-grid">
                <div className="date-field">
                  <label htmlFor="start-date-input" className="field-label">
                    Baseline Window Start:
                  </label>
                  <input
                    id="start-date-input"
                    type="date"
                    className="date-input"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>

                <div className="date-field">
                  <label htmlFor="end-date-input" className="field-label">
                    Observation Window End:
                  </label>
                  <input
                    id="end-date-input"
                    type="date"
                    className="date-input"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </div>
              </div>

              {dateError && (
                <div className="alert-box alert-error">
                  <span>❌ {dateError}</span>
                </div>
              )}

              <p className="educational-note">
                ℹ️ <strong>Sentinel-1 Revisit Notice:</strong> The Copernicus Sentinel-1 constellation operates on a
                12-day orbital repeat cycle (6 days with both S1A &amp; S1B active). Observations occur at distinct orbit tracks,
                not daily continuous sweeps.
              </p>

              {/* Action Button: Search Satellite Data */}
              <button
                type="button"
                className="btn btn-primary btn-search-catalog"
                onClick={handleSearchCatalog}
                disabled={isSearchingCatalog || !aoiValidation.isValid || Boolean(dateError)}
              >
                {isSearchingCatalog ? (
                  <>
                    <span className="spinner-inline" />
                    Searching NASA ASF / Copernicus Archive...
                  </>
                ) : (
                  '🔍 Search Satellite Data'
                )}
              </button>
            </div>

            {/* STEP 3: Catalogue Search Results & Scene Pairing */}
            {catalogError && (
              <div className="workflow-card alert-card">
                <div className="alert-box alert-error">
                  <span>{catalogError}</span>
                </div>
              </div>
            )}

            {catalogResponse && (
              <div className="workflow-card">
                <div className="step-badge-row">
                  <span className="step-num">Step 3</span>
                  <span className="step-label">Satellite Catalogue Matches</span>
                </div>
                <h3 className="card-title">Sentinel-1 Radar Observations</h3>

                <div className="catalog-stat-strip">
                  <div className="stat-chip">
                    <span className="chip-label">Total Scenes:</span>
                    <span className="chip-val">{catalogResponse.total_scenes}</span>
                  </div>
                  <div className="stat-chip">
                    <span className="chip-label">Compatible Pairs:</span>
                    <span className="chip-val highlight">{catalogResponse.compatible_pairs_count}</span>
                  </div>
                </div>

                {catalogResponse.compatible_pairs.length > 0 ? (
                  <div className="pairs-selector-section">
                    <label htmlFor="pair-select" className="field-label">
                      Select Verified Compatible Pair:
                    </label>
                    <select
                      id="pair-select"
                      className="pair-dropdown"
                      value={selectedPairIndex}
                      onChange={(e) => setSelectedPairIndex(Number(e.target.value))}
                    >
                      {catalogResponse.compatible_pairs.map((p, idx) => (
                        <option key={idx} value={idx}>
                          Pair #{idx + 1}: {p.baseline.acquisition_time.slice(0, 10)} &rarr; {p.change.acquisition_time.slice(0, 10)} (Δt = {p.temporal_baseline_days} days)
                        </option>
                      ))}
                    </select>

                    {selectedPair && (
                      <div className="pair-detail-card">
                        <div className="pair-scene-row">
                          <span className="scene-role">T1 Baseline:</span>
                          <span className="scene-name mono">{selectedPair.baseline.scene_name}</span>
                          <span className="scene-meta">
                            Orbit {selectedPair.baseline.relative_orbit} · {selectedPair.baseline.orbit_direction} · {selectedPair.baseline.polarization}
                          </span>
                        </div>

                        <div className="pair-scene-row">
                          <span className="scene-role">T2 Observation:</span>
                          <span className="scene-name mono">{selectedPair.change.scene_name}</span>
                          <span className="scene-meta">
                            Orbit {selectedPair.change.relative_orbit} · {selectedPair.change.orbit_direction} · {selectedPair.change.polarization}
                          </span>
                        </div>

                        <div className="compatibility-metrics-grid">
                          <div className="comp-metric-item">
                            <span className="metric-icon">✓</span>
                            <span>Track {selectedPair.metrics.track_match ? 'Matched' : 'Mismatched'}</span>
                          </div>
                          <div className="comp-metric-item">
                            <span className="metric-icon">✓</span>
                            <span>Direction {selectedPair.metrics.flight_direction_match ? 'Matched' : 'Mismatched'}</span>
                          </div>
                          <div className="comp-metric-item">
                            <span className="metric-icon">✓</span>
                            <span>Dual-Pol {selectedPair.metrics.polarization_match ? 'Verified' : 'Unverified'}</span>
                          </div>
                          <div className="comp-metric-item">
                            <span className="metric-icon">✓</span>
                            <span>Δt = {selectedPair.temporal_baseline_days} days</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="no-pairs-notice">
                    No geometrically compatible observation pairs found with identical orbit tracks and dual-polarization.
                    Consider broadening your date search window.
                  </p>
                )}

                {/* STEP 4: Processing Action */}
                <div className="processing-action-section">
                  <button
                    type="button"
                    className="btn btn-primary btn-submit-job"
                    onClick={handleStartAnalysis}
                    disabled={isSubmitting || !aoiValidation.isValid || Boolean(activeJob && activeJob.status === 'RUNNING') || Boolean(demoRestrictedNotice)}
                  >
                    {isSubmitting ? ( /* show spinner while submitting */
                      <>
                        <span className="spinner-inline" /> Submitting Request...
                      </>
                    ) : (
                      '⚡ Request Satellite Analysis'
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Public Demo Mode Security Notice */}
            {demoRestrictedNotice && (
              <div className="workflow-card security-notice-card">
                <div className="security-icon">🔒</div>
                <div className="security-content">
                  <h4 className="security-title">Public Demo Mode: Compute Protection Active</h4>
                  <p className="security-desc">{demoRestrictedNotice}</p>
                  <p className="security-desc sub">
                    To prevent denial of service and uncontrolled cloud compute costs, dynamic satellite ingestion is
                    restricted in public preview mode. You can inspect genuine verified Sentinel-1 campaigns right now:
                  </p>
                  <div className="demo-campaigns-action-row">
                    {Object.entries(ARCHIVED_CAMPAIGNS).map(([id, campaign]) => (
                      <Link
                        key={id}
                        to={`/explorer?run=${id}`}
                        className="btn btn-secondary btn-sm"
                      >
                        Explore {campaign.label} &rarr;
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* In-Flight / Terminal Job Status Card */}
            {activeJob && (
              <div className={`workflow-card job-status-card ${activeJob.status.toLowerCase()}`}>
                <div className="job-status-header">
                  <div className="status-indicator-group">
                    <span className={`status-dot ${activeJob.status.toLowerCase()}`} />
                    <span className="status-label">Job: {activeJob.run_id}</span>
                  </div>
                  <span className={`status-badge badge-${activeJob.status.toLowerCase()}`}>
                    {activeJob.status}
                  </span>
                </div>

                <div className="progress-bar-container">
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${Math.max(activeJob.progress_pct, 5)}%` }}
                  />
                </div>

                <div className="job-meta-row">
                  <span className="stage-text">Stage: <strong>{activeJob.stage || activeJob.status}</strong></span>
                  <span className="pct-text">{activeJob.progress_pct.toFixed(0)}%</span>
                </div>

                {activeJob.error && (
                  <div className="job-error-box">
                    <span>❌ {activeJob.error}</span>
                  </div>
                )}

                {activeJob.status === 'COMPLETED' && (
                  <div className="completed-actions-row">
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => navigate(`/explorer?run=${activeJob.run_id}`)}
                    >
                      🗺️ Open Map Explorer
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => navigate(`/comparison?run=${activeJob.run_id}`)}
                    >
                      ⚖️ View Flood Comparison
                    </button>
                  </div>
                )}

                {(activeJob.status === 'RUNNING' || activeJob.status === 'PENDING') && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm btn-cancel"
                    onClick={handleCancelJob}
                  >
                    ✕ Cancel Job
                  </button>
                )}
              </div>
            )}

            {submissionError && (
              <div className="alert-box alert-error">
                <span>❌ {submissionError}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

