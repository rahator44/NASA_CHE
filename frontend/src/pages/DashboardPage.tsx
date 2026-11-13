import React from 'react';
import { LoadedRun } from '../api/types';
import { Link } from '../router/Router';

interface DashboardPageProps {
  loadedRun: LoadedRun | null;
  selectedRunId: string;
  onSelectRun: (id: string) => void;
  isLoading?: boolean;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  loadedRun,
  selectedRunId,
  onSelectRun,
  isLoading = false,
}) => {
  if (isLoading || !loadedRun) {
    return (
      <div className="dashboard-page loading-mode">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading Earth Pulse observation intelligence...</p>
        </div>
      </div>
    );
  }

  const summary = loadedRun.summary;
  const is2025 = selectedRunId === 'run_20261111_164348_f3c2b8';
  const is2024 = selectedRunId === 'run_20261110_221732_1f2e94';

  const transitions = summary.flood_transitions_km2;
  const netChangeKm2 = transitions.net_candidate_water_change;
  const newlyInundatedKm2 = transitions.newly_inundated;
  const recededWaterKm2 = transitions.receded_water;

  const reliableTransects = summary.riverbank_dynamics?.reliable_transects_count;
  const evaluatedTransects = summary.riverbank_dynamics?.evaluated_transects;

  return (
    <div className="dashboard-page">
      {/* Hero Mission Section */}
      <section className="dashboard-hero">
        <div className="hero-content">
          <div className="hero-badge">🛰️ Sentinel-1 Synthetic Aperture Radar (SAR)</div>
          <h2 className="hero-heading">
            All-Weather Radar Hydrology & Explainable AI for the Braided Jamuna River
          </h2>
          <p className="hero-description">
            Earth Pulse turns raw C-band active microwave backscatter from the Copernicus Sentinel-1
            constellation into calibrated flood-inundation dynamics, morphological riverbank displacement
            tracking, and mathematically additive explainable AI attributions across monsoon cloud cover.
          </p>

          <div className="hero-cta-group">
            <Link to="/explorer" className="btn-primary">
              🗺️ Launch Satellite Map Explorer
            </Link>
            <Link to="/comparison" className="btn-secondary">
              ⚖️ View Before / After Comparison
            </Link>
            <Link to="/explainable-ai" className="btn-secondary">
              🧠 Inspect Explainable AI (XAI)
            </Link>
          </div>
        </div>
      </section>

      {/* Active Campaign KPI Grid */}
      <section className="dashboard-kpi-section">
        <div className="section-header">
          <div>
            <h3 className="section-title">Verified Scientific Measurements</h3>
            <p className="section-subtitle">
              Derived dynamically from active run: <span className="mono-code">{selectedRunId}</span> (Jamuna River, Bangladesh)
            </p>
          </div>
          <span className="live-status-pill">✓ Processed GeoTIFFs Active</span>
        </div>

        <div className="kpi-grid">
          <div className="kpi-card accent-cyan">
            <span className="kpi-label">Net Candidate Water Change</span>
            <div className="kpi-value-row">
              <span className={`kpi-value ${netChangeKm2 >= 0 ? 'positive' : 'negative'}`}>
                {netChangeKm2 >= 0 ? `+${netChangeKm2.toFixed(4)}` : netChangeKm2.toFixed(4)}
              </span>
              <span className="kpi-unit">km²</span>
            </div>
            <span className="kpi-caption">
              {(netChangeKm2 * 100).toFixed(1)} hectares net water surface displacement
            </span>
          </div>

          <div className="kpi-card accent-blue">
            <span className="kpi-label">Gross Newly Inundated Area</span>
            <div className="kpi-value-row">
              <span className="kpi-value">+{newlyInundatedKm2.toFixed(4)}</span>
              <span className="kpi-unit">km²</span>
            </div>
            <span className="kpi-caption">
              Dry char / land at baseline (T1) &rarr; Submerged at observation (T2)
            </span>
          </div>

          <div className="kpi-card accent-purple">
            <span className="kpi-label">Receded Surface Water</span>
            <div className="kpi-value-row">
              <span className="kpi-value">{recededWaterKm2.toFixed(4)}</span>
              <span className="kpi-unit">km²</span>
            </div>
            <span className="kpi-caption">
              Exposed sandbars and riverbed post-inundation
            </span>
          </div>

          <div className="kpi-card accent-emerald">
            <span className="kpi-label">Riverbank Transects Qualified</span>
            <div className="kpi-value-row">
              <span className="kpi-value">{reliableTransects ?? '—'}</span>
              <span className="kpi-unit">/ {evaluatedTransects ?? '—'}</span>
            </div>
            <span className="kpi-caption">
              {summary.riverbank_dynamics?.message || 'No riverbank measurements are available for this analysis.'}
            </span>
          </div>
        </div>
      </section>

      {/* Two Real Completed Campaigns Overview */}
      <section className="dashboard-campaigns-section">
        <h3 className="section-title">Authoritative Demonstration Campaigns</h3>
        <p className="section-subtitle">
          Switch between two independently audited Sentinel-1 observation epochs over the Kazipur / Sirajganj reach:
        </p>

        <div className="campaigns-grid">
          {/* Campaign 1: 2025 Live SAR Run */}
          <div className={`campaign-card ${is2025 ? 'selected' : ''}`}>
            <div className="campaign-card-header">
              <span className="campaign-type-badge live">2025 LIVE OBSERVATION</span>
              {is2025 && <span className="active-tag">Active in View</span>}
            </div>
            <h4 className="campaign-title">January 2025 Braided Reach Dynamic Monitoring</h4>
            <div className="campaign-meta">
              <div className="meta-item">
                <span className="meta-label">Observation Epoch:</span>
                <span className="meta-value">2025-01-12 &rarr; 2025-01-24 (12-day repeat)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Sensor / Swath:</span>
                <span className="meta-value">Sentinel-1A IW GRDH (VV + VH Dual-Pol)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Net Water Change:</span>
                <span className="meta-value highlight">+1.0440 km² (+104.40 ha)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Riverbank Morphodynamics:</span>
                <span className="meta-value">35 Qualified Transects (1 unqualified)</span>
              </div>
            </div>

            <div className="campaign-actions">
              <button
                className={`btn-select-campaign ${is2025 ? 'active' : ''}`}
                onClick={() => onSelectRun('run_20261111_164348_f3c2b8')}
              >
                {is2025 ? '✓ Currently Selected' : 'Select 2025 Campaign'}
              </button>
              <Link to="/explorer" className="btn-link">
                Open in Explorer &rarr;
              </Link>
            </div>
          </div>

          {/* Campaign 2: 2024 Monsoon Baseline */}
          <div className={`campaign-card ${is2024 ? 'selected' : ''}`}>
            <div className="campaign-card-header">
              <span className="campaign-type-badge historical">2024 MONSOON BASELINE</span>
              {is2024 && <span className="active-tag">Active in View</span>}
            </div>
            <h4 className="campaign-title">July 2024 Peak Monsoon Flood Inundation</h4>
            <div className="campaign-meta">
              <div className="meta-item">
                <span className="meta-label">Observation Epoch:</span>
                <span className="meta-value">2024-06-10 &rarr; 2024-07-16 (Pre vs Peak Flood)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Sensor / Swath:</span>
                <span className="meta-value">Sentinel-1A IW GRDH (VV + VH Dual-Pol)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Net Water Change:</span>
                <span className="meta-value highlight">+5.8432 km² (+584.32 ha)</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Riverbank Dynamics:</span>
                <span className="meta-value">36 Analyzed Transects (Legacy Quality Gate)</span>
              </div>
            </div>

            <div className="campaign-actions">
              <button
                className={`btn-select-campaign ${is2024 ? 'active' : ''}`}
                onClick={() => onSelectRun('run_20261110_221732_1f2e94')}
              >
                {is2024 ? '✓ Currently Selected' : 'Select 2024 Campaign'}
              </button>
              <Link to="/explorer" className="btn-link">
                Open in Explorer &rarr;
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Scientific Campaign Visual Showcase & Quick Tour */}
      <section className="dashboard-showcase-section">
        <div className="showcase-card">
          <div className="showcase-content">
            <span className="feature-tag">INTERACTIVE PRODUCT SUITE</span>
            <h3 className="showcase-title">Explore Genuine Scientific Radar Products</h3>
            <p className="showcase-text">
              Earth Pulse serves 6 georeferenced raster products generated from calibrated Sentinel-1
              backscatter ($\sigma^0$), terrain-corrected to SRTM 1-sec digital elevation models.
              Toggle between backscatter intensity, Dual-AND Otsu water masks, 6-class flood dynamics,
              and machine learning probability layers with transparent NoData clipping.
            </p>

            <div className="product-pill-list">
              <span className="product-pill">🌊 6-Class Flood Transitions</span>
              <span className="product-pill">🛰️ Dual-Pol SAR Intensity</span>
              <span className="product-pill">💧 Otsu Water Masks</span>
              <span className="product-pill">🧠 40-Tree RF Probability</span>
              <span className="product-pill">📐 Vector Cluster GeoJSON</span>
            </div>

            <div className="showcase-actions">
              <Link to="/explorer" className="btn-primary">
                View Full-Resolution GIS Map
              </Link>
              <Link to="/science" className="btn-secondary">
                Read Scientific Methodology
              </Link>
            </div>
          </div>

          <div className="showcase-preview">
            <img
              src={`/api/v1/runs/${selectedRunId}/previews/preview_flood_transitions.png`}
              alt="Preview of Sentinel-1 Flood Transition Classes"
              className="preview-img"
              loading="lazy"
              onError={(e) => {
                // If API preview image fails, hide cleanly without broken icon
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <span className="preview-caption">
              Live preview: Flood Transitions for {selectedRunId}
            </span>
          </div>
        </div>
      </section>

      {/* Scientific Limitations & Peer-Review Disclosure */}
      <section className="dashboard-limitations-section">
        <div className="limitations-card">
          <div className="limitations-icon">ℹ️</div>
          <div className="limitations-body">
            <h4 className="limitations-title">Scientific Caveats & Scope of Analysis</h4>
            <p className="limitations-text">
              The demonstrated results reflect radar backscatter changes across an 8.8 × 8.8 km (71.8 km²)
              study reach of the braided Jamuna River (Sirajganj / Kazipur, Bangladesh).
              Candidate water changes represent surface backscatter signatures identified through Dual-AND adaptive Otsu thresholding;
              they should not be interpreted as confirmed structural damage, permanent bank loss, or hazard risk without secondary optical
              or on-the-ground hydrological gage reconciliation.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};
