import React, { useState } from 'react';
import { LoadedRun } from '../api/types';
import { JamunaMap } from '../components/Map/JamunaMap';
import { LoadingState } from '../components/Common/LoadingState';
import { Link } from '../router/Router';

interface ComparisonPageProps {
  loadedRun: LoadedRun | null;
  selectedRunId: string;
  onSelectRun?: (runId: string) => void;
  isLoading?: boolean;
}

export const ComparisonPage: React.FC<ComparisonPageProps> = ({
  loadedRun,
  selectedRunId,
  isLoading = false,
}) => {
  const [t1Layer, setT1Layer] = useState<'t1_sar' | 't1_water'>('t1_sar');
  const [t2Layer, setT2Layer] = useState<'t2_sar' | 't2_water' | 'transitions'>('transitions');

  if (isLoading || !loadedRun) {
    return (
      <div className="comparison-page loading-mode">
        <LoadingState message={`Loading hydrological comparison data for ${selectedRunId}...`} />
      </div>
    );
  }

  const summary = loadedRun.summary;
  const manifest = loadedRun.manifest;
  const obs = summary.observations;
  const transitions = summary.flood_transitions_km2;

  const baselineDate = obs.baseline?.acquisition_time?.slice(0, 10) || 'Date unavailable';
  const comparisonDate = obs.change?.acquisition_time?.slice(0, 10) || 'Date unavailable';
  const netChange = transitions.net_candidate_water_change;
  const newlyInundated = transitions.newly_inundated;
  const recededWater = transitions.receded_water;
  const persistentWater = transitions.persistent_water;
  const persistentLand = transitions.persistent_non_water || 0;
  const commonValid = persistentWater + newlyInundated + recededWater + persistentLand;

  return (
    <div className="comparison-page">
      {/* Header Bar */}
      <div className="comparison-header">
        <div className="header-info">
          <div className="badge-row">
            <span className="badge badge-cyan">Campaign: {selectedRunId}</span>
            <Link to="/explorer" className="badge badge-outline">🗺️ Open in Explorer</Link>
            <Link to="/explainable-ai" className="badge badge-outline">🧠 Inspect XAI</Link>
          </div>
          <h2 className="page-heading">Dual-Epoch Flood &amp; Riverbank Comparison</h2>
          <p className="page-subheading">
            Synchronized Sentinel-1 C-band SAR observations across the Jamuna braided reach.
          </p>
        </div>

        <div className="epoch-summary-badge">
          <span className="epoch-dates">
            📅 {baselineDate} &rarr; {comparisonDate}
          </span>
          <span className="epoch-delta">
            Net Change: {netChange >= 0 ? `+${netChange.toFixed(4)}` : netChange.toFixed(4)} km²
          </span>
        </div>
      </div>

      {/* Synchronized Side-by-Side Map Experience */}
      <div className="dual-map-section">
        {/* Left Map: Baseline (T1) */}
        <div className="map-panel left-panel">
          <div className="panel-header">
            <div className="panel-title-group">
              <span className="epoch-tag baseline">T1 BASELINE</span>
              <h3 className="panel-title">Baseline Observation ({baselineDate})</h3>
            </div>
            <div className="panel-layer-toggles">
              <button
                className={`panel-toggle-btn ${t1Layer === 't1_sar' ? 'active' : ''}`}
                onClick={() => setT1Layer('t1_sar')}
              >
                🛰️ SAR Intensity
              </button>
              <button
                className={`panel-toggle-btn ${t1Layer === 't1_water' ? 'active' : ''}`}
                onClick={() => setT1Layer('t1_water')}
              >
                💧 Water Mask
              </button>
            </div>
          </div>

          <div className="comparison-map-wrapper">
            <JamunaMap
              runId={loadedRun.runId}
              manifest={manifest}
              summary={summary}
              activeLayer={t1Layer}
              onLayerChange={() => {}}
              standalone={true}
            />
          </div>

          <div className="panel-footer-meta">
            <span>Scene: <span className="mono-code">{obs.baseline?.scene_name || 'Unavailable'}</span></span>
            <span>Threshold VV: <span className="mono-code">{obs.baseline?.threshold_vv_db != null ? `${obs.baseline.threshold_vv_db.toFixed(2)} dB` : 'Unavailable'}</span></span>
          </div>
        </div>

        {/* Right Map: Comparison (T2) / Dynamics */}
        <div className="map-panel right-panel">
          <div className="panel-header">
            <div className="panel-title-group">
              <span className="epoch-tag observation">T2 OBSERVATION</span>
              <h3 className="panel-title">Post-Inundation ({comparisonDate})</h3>
            </div>
            <div className="panel-layer-toggles">
              <button
                className={`panel-toggle-btn ${t2Layer === 'transitions' ? 'active' : ''}`}
                onClick={() => setT2Layer('transitions')}
              >
                🌊 Flood Transitions
              </button>
              <button
                className={`panel-toggle-btn ${t2Layer === 't2_sar' ? 'active' : ''}`}
                onClick={() => setT2Layer('t2_sar')}
              >
                🛰️ SAR Intensity
              </button>
              <button
                className={`panel-toggle-btn ${t2Layer === 't2_water' ? 'active' : ''}`}
                onClick={() => setT2Layer('t2_water')}
              >
                💧 Water Mask
              </button>
            </div>
          </div>

          <div className="comparison-map-wrapper">
            <JamunaMap
              runId={loadedRun.runId}
              manifest={manifest}
              summary={summary}
              activeLayer={t2Layer}
              onLayerChange={() => {}}
              standalone={true}
            />
          </div>

          <div className="panel-footer-meta">
            <span>Scene: <span className="mono-code">{obs.change?.scene_name || 'S1A_GRDH_T2'}</span></span>
            <span>Threshold VV: <span className="mono-code">{obs.change?.threshold_vv_db != null ? `${obs.change.threshold_vv_db.toFixed(2)} dB` : 'Unavailable'}</span></span>
          </div>
        </div>
      </div>

      {/* Hydrological Transition Accounting Breakdown */}
      <section className="transition-accounting-section">
        <h3 className="section-title">Surface Water Transition Breakdown</h3>
        <p className="section-subtitle">
          Accounting of classified pixel transitions within the common valid study polygon (EPSG:32645):
        </p>

        <div className="accounting-cards-grid">
          <div className="accounting-card highlight-cyan">
            <div className="card-top">
              <span className="status-bullet cyan"></span>
              <span className="card-name">Newly Inundated</span>
            </div>
            <div className="card-number">+{newlyInundated.toFixed(4)} km²</div>
            <p className="card-desc">
              Non-water land at T1 ({baselineDate}) converted to water signature at T2 ({comparisonDate}).
            </p>
          </div>

          <div className="accounting-card highlight-orange">
            <div className="card-top">
              <span className="status-bullet orange"></span>
              <span className="card-name">Receded Surface Water</span>
            </div>
            <div className="card-number">-{recededWater.toFixed(4)} km²</div>
            <p className="card-desc">
              Water signature at T1 that receded to expose dry sandbars or charland by T2.
            </p>
          </div>

          <div className="accounting-card highlight-blue">
            <div className="card-top">
              <span className="status-bullet blue"></span>
              <span className="card-name">Persistent Channel Water</span>
            </div>
            <div className="card-number">{persistentWater.toFixed(4)} km²</div>
            <p className="card-desc">
              Permanent braided channels with consistent water signature across both acquisitions.
            </p>
          </div>

          <div className="accounting-card highlight-emerald">
            <div className="card-top">
              <span className="status-bullet emerald"></span>
              <span className="card-name">Net Candidate Water Change</span>
            </div>
            <div className="card-number">
              {netChange >= 0 ? `+${netChange.toFixed(4)}` : netChange.toFixed(4)} km²
            </div>
            <p className="card-desc">
              Net balance: Newly Inundated ({newlyInundated.toFixed(2)} km²) minus Receded ({recededWater.toFixed(2)} km²).
            </p>
          </div>
        </div>
      </section>

      {/* Riverbank Morphodynamics Section */}
      <section className="riverbank-dynamics-section">
        <div className="riverbank-card">
          <div className="riverbank-header">
            <h4 className="card-title">📐 Riverbank Correspondence & Morphodynamics</h4>
            <span className="quality-pill">
              {summary.riverbank_dynamics?.reliable_transects_count ? 'Spatial Quality Gated' : 'Legacy Uncalibrated'}
            </span>
          </div>

          <div className="riverbank-stats-row">
            <div className="stat-box">
              <span className="stat-label">Evaluated Transects</span>
              <span className="stat-value">{summary.riverbank_dynamics?.evaluated_transects ?? '—'}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Reliable Correspondence</span>
              <span className="stat-value">
                {summary.riverbank_dynamics?.reliable_transects_count ?? 'Not assessed'}
              </span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Unqualified Transects</span>
              <span className="stat-value">
                {summary.riverbank_dynamics?.unqualified_transects_count ?? 'Not assessed'}
              </span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Study Footprint</span>
              <span className="stat-value">{commonValid.toFixed(1)} km²</span>
            </div>
          </div>

          <p className="riverbank-note">
            {summary.riverbank_dynamics?.unqualified_transects_count
              ? 'Transects are evaluated under strict geometric correspondence to prevent transient sandbar migration from being falsely cataloged as permanent embankment erosion.'
              : '36 analyzed transects — correspondence quality not evaluated (legacy data).'}
          </p>
        </div>
      </section>

      {/* Explicit Scientific Caveats */}
      <section className="scientific-caveats-box">
        <div className="caveat-header">⚠️ Scientific Classification Notice</div>
        <p className="caveat-body">
          Candidate water changes reflect automated radiometric thresholding of Sentinel-1 active radar backscatter.
          While C-band microwaves penetrate cloud cover, surface specular reflectance can be modulated by high wind-driven waves,
          saturated mudflats, and emergent vegetation. Candidate water change values must not be cited as confirmed permanent
          disaster damage without ground-level hydrological gauge verification.
        </p>
      </section>
    </div>
  );
};
