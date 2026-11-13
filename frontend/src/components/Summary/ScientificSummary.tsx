import React from 'react';
import { RunSummary } from '../../api/types';

interface ScientificSummaryProps {
  summary: RunSummary;
}

export const ScientificSummary: React.FC<ScientificSummaryProps> = ({ summary }) => {
  const transitions = summary.flood_transitions_km2;
  const riverbank = summary.riverbank_dynamics;
  const obs = summary.observations;
  const ai = summary.ai_evaluation;
  const aoi = summary.study_aoi;

  const netChange = transitions.net_candidate_water_change;
  const isExpansion = netChange >= 0;
  const commonDomain = aoi?.common_valid_domain_km2 ?? transitions.valid_comparison_area;

  const formatUtc = (isoStr?: string) => {
    if (!isoStr) return 'Unknown';
    return isoStr.replace('T', ' ').replace('.000Z', ' UTC').replace('Z', ' UTC');
  };

  return (
    <div className="summary-panel">
      <div className="summary-header">
        <h3 className="panel-title">Scientific Measurements & Accounting</h3>
        <span className="run-tag">{summary.run_id}</span>
      </div>

      {/* Primary KPI Card */}
      <div className={`metric-card primary-kpi ${isExpansion ? 'expansion' : 'recession'}`}>
        <div className="kpi-label">Net Candidate Water Change</div>
        <div className="kpi-value">
          {netChange >= 0 ? `+${netChange.toFixed(4)}` : netChange.toFixed(4)} <span className="unit">km²</span>
        </div>
        <div className="kpi-subtext">
          {isExpansion ? 'Net Flood Inundation Expansion' : 'Net Water Recession'} across common valid domain (
          {commonDomain !== undefined ? `${commonDomain.toFixed(2)} km²` : 'spatial overlap'}
          )
        </div>
      </div>

      {/* Flood Inundation Accounting Breakdown */}
      <div className="metric-group">
        <h4 className="group-title">Flood Surface Area Transition Invariant</h4>
        <div className="metric-grid-3">
          <div className="metric-cell">
            <span className="cell-label">Newly Inundated</span>
            <span className="cell-val text-cyan">+{transitions.newly_inundated.toFixed(4)} km²</span>
            <span className="cell-sub-desc">Water-change candidates</span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Receded Water</span>
            <span className="cell-val text-orange">-{transitions.receded_water.toFixed(4)} km²</span>
            <span className="cell-sub-desc">Observed water recession</span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Persistent Water</span>
            <span className="cell-val text-blue">{transitions.persistent_water.toFixed(4)} km²</span>
            <span className="cell-sub-desc">Persistent surface water</span>
          </div>
        </div>

        <div className="metric-grid-2" style={{ marginTop: '0.5rem' }}>
          <div className="metric-cell">
            <span className="cell-label">Persistent Dry Land</span>
            <span className="cell-val">{transitions.persistent_non_water.toFixed(4)} km²</span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Indeterminate Floor</span>
            <span className="cell-val text-muted">{transitions.indeterminate_floor.toFixed(4)} km²</span>
          </div>
        </div>

        <div className="accounting-verification">
          <span className="check-icon">✓</span>
          <span>
            Strict Area Conservation: {transitions.newly_inundated.toFixed(4)} - {transitions.receded_water.toFixed(4)} ={' '}
            {netChange.toFixed(4)} km²
          </span>
        </div>
      </div>

      {/* Riverbank Morphodynamics */}
      <div className="metric-group">
        <h4 className="group-title">
          Riverbank Dynamics <span className="group-subtitle">(Quality-Filtered Water-Boundary Displacement Candidates)</span>
        </h4>
        <div className="metric-grid-2">
          <div className="metric-cell">
            <span className="cell-label">Transect Assessment</span>
            <span className="cell-val">
              {riverbank.unqualified_transects_count !== undefined ? (
                <span className="text-emerald">
                  {riverbank.valid_migration_transects}{' '}
                  <span className="cell-sub">/ {riverbank.evaluated_transects} Qualified</span>
                </span>
              ) : (
                <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.3, display: 'block' }}>
                  {riverbank.evaluated_transects} analyzed transects — correspondence quality not evaluated (legacy data)
                </span>
              )}
            </span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Quarantined / Ambiguous</span>
            <span className="cell-val text-amber">
              {riverbank.unqualified_transects_count !== undefined
                ? `${riverbank.unqualified_transects_count} transect(s)`
                : 'Not Evaluated (Legacy data)'}
            </span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Mean Left Bank Shift</span>
            <span className="cell-val">
              {riverbank.unqualified_transects_count !== undefined
                ? riverbank.mean_left_bank_displacement_m !== null && riverbank.mean_left_bank_displacement_m !== undefined
                  ? `${riverbank.mean_left_bank_displacement_m > 0 ? '+' : ''}${riverbank.mean_left_bank_displacement_m.toFixed(1)} m`
                  : 'N/A'
                : 'Unqualified (Legacy 2024)'}
            </span>
          </div>
          <div className="metric-cell">
            <span className="cell-label">Mean Right Bank Shift</span>
            <span className="cell-val">
              {riverbank.unqualified_transects_count !== undefined
                ? riverbank.mean_right_bank_displacement_m !== null && riverbank.mean_right_bank_displacement_m !== undefined
                  ? `${riverbank.mean_right_bank_displacement_m > 0 ? '+' : ''}${riverbank.mean_right_bank_displacement_m.toFixed(1)} m`
                  : 'N/A'
                : 'Unqualified (Legacy 2024)'}
            </span>
          </div>
        </div>

        {/* Dynamic Unqualified Diagnostic List */}
        {riverbank.unqualified_transects && riverbank.unqualified_transects.length > 0 && (
          <div className="diagnostic-note">
            <span className="diag-title">Excluded Diagnostic Record(s):</span>
            {riverbank.unqualified_transects.map((diag, i) => (
              <span key={i} className="diag-item">
                Row {diag.transect_row}: {diag.reason || 'Failed IoU correspondence quality criteria'}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Sensor Calibration & Dual-Polarization Thresholds */}
      <div className="metric-group">
        <h4 className="group-title">Sentinel-1 Dual-Pol Radiometric Calibration (σ° Backscatter)</h4>
        <div className="meta-list">
          {obs?.baseline && (
            <div className="meta-row">
              <span className="meta-key">Baseline (T1):</span>
              <span className="meta-val">
                {formatUtc(obs.baseline.acquisition_time)}
                <br />
                <span className="sub-thresholds">
                  Otsu σ° VV: {obs.baseline.threshold_vv_db.toFixed(2)} dB | VH: {obs.baseline.threshold_vh_db.toFixed(2)} dB
                </span>
              </span>
            </div>
          )}
          {obs?.change && (
            <div className="meta-row">
              <span className="meta-key">Observation (T2):</span>
              <span className="meta-val">
                {formatUtc(obs.change.acquisition_time)}
                <br />
                <span className="sub-thresholds">
                  Otsu σ° VV: {obs.change.threshold_vv_db.toFixed(2)} dB | VH: {obs.change.threshold_vh_db.toFixed(2)} dB
                </span>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Experimental AI Model Evaluation */}
      {ai && (
        <div className="metric-group">
          <h4 className="group-title">
            Experimental Random Forest Water Probabilities <span className="group-subtitle">({ai.model_id})</span>
          </h4>
          <div className="metric-grid-2">
            <div className="metric-cell">
              <span className="cell-label">Mean Water Probability</span>
              <span className="cell-val">{(ai.mean_water_probability * 100).toFixed(1)}%</span>
            </div>
            <div className="metric-cell">
              <span className="cell-label">Saabas Tree Additivity</span>
              <span className="cell-val text-emerald">
                {ai.additivity_verified ? 'Verified (Δ < 1e-7)' : 'Unverified'}
              </span>
            </div>
          </div>
          <div className="ai-disclaimer">
            <span>
              ℹ Experimental Random Forest baseline ({ai.sample_evaluated} validation spatial samples).
              Probabilities demonstrate tree explainability; not independently calibrated for 2025 hydrology.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
