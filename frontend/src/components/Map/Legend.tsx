import React, { useState } from 'react';
import { VisualLayer, RunSummary } from '../../api/types';

interface LegendProps {
  activeLayer: string;
  layer?: VisualLayer;
  summary?: RunSummary;
}

export const Legend: React.FC<LegendProps> = ({ activeLayer, layer, summary }) => {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const transitions = summary?.flood_transitions_km2;

  // Determine active title
  const getLayerTitle = () => {
    if (activeLayer === 'transitions') return '6-Class Flood Dynamics';
    if (activeLayer === 't1_water') return 'Baseline (T1) Water';
    if (activeLayer === 't2_water') return 'Observation (T2) Water';
    if (activeLayer === 't1_sar') return 'Baseline (T1) Backscatter';
    if (activeLayer === 't2_sar') return 'Observation (T2) Backscatter';
    if (activeLayer === 'rf_probability') return 'RF Water Probability';
    return layer?.title || 'Layer Info';
  };

  const activeTitle = getLayerTitle();

  if (isCollapsed) {
    return (
      <div
        className="map-legend collapsed"
        onClick={() => setIsCollapsed(false)}
        title="Tap to expand legend"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            setIsCollapsed(false);
          }
        }}
      >
        <span className="legend-title">
          🗺️ Legend: {activeTitle} <span className="legend-toggle-hint">▲ Expand</span>
        </span>
      </div>
    );
  }

  // Case 1: Flood Transitions (6-Class)
  if (activeLayer === 'transitions') {
    const classes = [
      {
        value: 1,
        label: 'Persistent Water',
        color: '#08519c',
        area: transitions?.persistent_water,
        desc: 'Inundated at both baseline (T1) and observation (T2)',
      },
      {
        value: 2,
        label: 'Newly Inundated (Water-Change Candidates)',
        color: '#41b6c4',
        area: transitions?.newly_inundated,
        desc: 'Dry land at T1 → Surface water at T2 (Expansion candidates)',
      },
      {
        value: 3,
        label: 'Receded Water (Observed Water Recession)',
        color: '#fe9929',
        area: transitions?.receded_water,
        desc: 'Surface water at T1 → Dry land/char at T2 (Observed recession)',
      },
      {
        value: 4,
        label: 'Persistent Non-Water Land',
        color: '#cccccc',
        area: transitions?.persistent_non_water,
        desc: 'Uninundated dry ground at both dates',
      },
      {
        value: 5,
        label: 'Indeterminate Floor',
        color: '#a6cee3',
        area: transitions?.indeterminate_floor,
        desc: 'Radar backscatter below sensor noise floor (<-28 dB)',
      },
      {
        value: 6,
        label: 'Outside AOI / NoData',
        color: 'transparent',
        borderColor: '#718096',
        area: transitions?.outside_polygon_nodata_area,
        desc: 'Outside study polygon boundary (100% Transparent NoData)',
        isTransparent: true,
      },
    ];

    return (
      <div className="map-legend">
        <div className="legend-header" onClick={() => setIsCollapsed(true)} title="Tap to collapse legend">
          <h4 className="legend-title">6-Class Flood Dynamics Legend</h4>
          <button className="legend-toggle-btn" aria-label="Collapse legend" type="button">
            ▼
          </button>
        </div>
        <div className="legend-list">
          {classes.map((cls) => (
            <div key={cls.value} className="legend-item">
              <span
                className={`legend-swatch ${cls.isTransparent ? 'swatch-transparent' : ''}`}
                style={{
                  backgroundColor: cls.color,
                  borderColor: cls.borderColor || 'transparent',
                }}
              />
              <div className="legend-text">
                <div className="legend-label-row">
                  <span className="legend-label">{cls.label}</span>
                  {cls.area !== undefined && cls.area !== null && (
                    <span className="legend-area">{cls.area.toFixed(2)} km²</span>
                  )}
                </div>
                <span className="legend-desc">{cls.desc}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Case 2: Single-date Candidate Water (T1 or T2)
  if (activeLayer === 't1_water' || activeLayer === 't2_water') {
    const isT1 = activeLayer === 't1_water';
    const obs = isT1 ? summary?.observations.baseline : summary?.observations.change;
    const legendClasses = layer?.legend?.classes || [
      { value: 1, label: 'Candidate Water', color: '#08519c', area_km2: obs?.water_area_km2 },
      { value: 0, label: 'Non-Water Land', color: '#d9d9d9', area_km2: null },
      { value: 2, label: 'Indeterminate Noise Floor', color: '#a6cee3', area_km2: null },
    ];

    return (
      <div className="map-legend">
        <div className="legend-header" onClick={() => setIsCollapsed(true)} title="Tap to collapse legend">
          <h4 className="legend-title">
            {isT1 ? 'Baseline (T1) Water Classification' : 'Observation (T2) Water Classification'}
          </h4>
          <button className="legend-toggle-btn" aria-label="Collapse legend" type="button">
            ▼
          </button>
        </div>
        <div className="legend-list">
          {legendClasses.map((cls) => (
            <div key={cls.value} className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: cls.color }} />
              <div className="legend-text">
                <div className="legend-label-row">
                  <span className="legend-label">{cls.label}</span>
                  {cls.area_km2 !== undefined && cls.area_km2 !== null && (
                    <span className="legend-area">{cls.area_km2.toFixed(2)} km²</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        {obs && (
          <p className="legend-caption">
            Scene: {obs.scene_name.split('_').slice(0, 3).join('_')}... | Otsu σ° VV: {obs.threshold_vv_db.toFixed(1)} dB, VH: {obs.threshold_vh_db.toFixed(1)} dB
          </p>
        )}
      </div>
    );
  }

  // Case 3: Continuous SAR Backscatter (t1_sar or t2_sar)
  if (activeLayer === 't1_sar' || activeLayer === 't2_sar') {
    const minDb = layer?.legend?.min_db ?? -25.0;
    const maxDb = layer?.legend?.max_db ?? 0.0;
    const isT1 = activeLayer === 't1_sar';

    return (
      <div className="map-legend">
        <div className="legend-header" onClick={() => setIsCollapsed(true)} title="Tap to collapse legend">
          <h4 className="legend-title">
            {isT1 ? 'Baseline Radar Backscatter (T1 VV σ°)' : 'Observation Radar Backscatter (T2 VV σ°)'}
          </h4>
          <button className="legend-toggle-btn" aria-label="Collapse legend" type="button">
            ▼
          </button>
        </div>
        <div className="sar-gradient-bar"></div>
        <div className="sar-gradient-labels">
          <span>{minDb.toFixed(1)} dB (Specular Water / Smooth)</span>
          <span>{maxDb.toFixed(1)} dB (Rough Land / Veg)</span>
        </div>
        <p className="legend-caption">
          Calibrated Sentinel-1 σ° (Sigma-0) copolarized backscatter intensity in decibels (dB)
        </p>
      </div>
    );
  }

  // Case 4: Random Forest Water Probability (rf_probability)
  if (activeLayer === 'rf_probability') {
    const threshold = layer?.legend?.decision_threshold ?? 0.35;
    return (
      <div className="map-legend">
        <div className="legend-header" onClick={() => setIsCollapsed(true)} title="Tap to collapse legend">
          <h4 className="legend-title">Experimental Random Forest Water Probability</h4>
          <button className="legend-toggle-btn" aria-label="Collapse legend" type="button">
            ▼
          </button>
        </div>
        <div className="rf-gradient-bar"></div>
        <div className="rf-gradient-labels">
          <span>0.0 (Land)</span>
          <span className="threshold-marker">{threshold.toFixed(2)} (Cutoff)</span>
          <span>1.0 (Water)</span>
        </div>
        <p className="legend-caption">
          Cividis colormap: Decision threshold p ≥ {threshold.toFixed(2)} classifies experimental water candidate
        </p>
      </div>
    );
  }

  // Fallback generic layer legend
  return (
    <div className="map-legend">
      <div className="legend-header" onClick={() => setIsCollapsed(true)} title="Tap to collapse legend">
        <h4 className="legend-title">{layer?.title || 'Layer Info'}</h4>
        <button className="legend-toggle-btn" aria-label="Collapse legend" type="button">
          ▼
        </button>
      </div>
      <p className="legend-caption">Type: {layer?.type || 'Raster'}</p>
    </div>
  );
};
