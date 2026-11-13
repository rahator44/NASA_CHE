import React from 'react';
import { ExplanationsResponse } from '../api/types';
import { XaiPanel } from '../components/Xai/XaiPanel';
import { Link } from '../router/Router';

interface XaiPageProps {
  explanations: ExplanationsResponse | null;
  selectedRunId: string;
  loading?: boolean;
}

export const XaiPage: React.FC<XaiPageProps> = ({
  explanations,
  selectedRunId,
  loading = false,
}) => {
  return (
    <div className="page-container xai-page">
      <div className="page-header xai-page-header">
        <div className="page-header-text">
          <div className="badge-row">
            <span className="badge badge-purple">Scientific Machine Learning</span>
            <span className="badge badge-cyan">Saabas Tree Path Decomposition</span>
            <span className="badge badge-outline">Run: {selectedRunId}</span>
          </div>
          <h1 className="page-title">Explainable AI (XAI) Attribution</h1>
          <p className="page-subtitle">
            Local feature importance decomposition explaining how Sentinel-1 SAR polarimetric
            and textural features drive candidate floodwater predictions.
          </p>
        </div>
        <div className="page-header-actions">
          <Link href="/explorer?layer=rf_probability" className="btn btn-primary action-btn">
            🗺️ Inspect Probability Map in Explorer
          </Link>
        </div>
      </div>

      {/* Model Architecture & Integrity Metadata */}
      <div className="xai-meta-grid">
        <div className="card meta-card">
          <div className="meta-card-header">
            <span className="meta-icon">🌲</span>
            <span className="meta-label">Frozen Experimental Model</span>
          </div>
          <div className="meta-value">Random Forest</div>
          <div className="meta-detail">40 Trees · Max Depth 6 · Min Leaf 10</div>
        </div>

        <div className="card meta-card">
          <div className="meta-card-header">
            <span className="meta-icon">⚖️</span>
            <span className="meta-label">Attribution Method</span>
          </div>
          <div className="meta-value">Exact Saabas (2014)</div>
          <div className="meta-detail">Saabas path additivity · Not exact TreeSHAP</div>
        </div>

        <div className="card meta-card">
          <div className="meta-card-header">
            <span className="meta-icon">🎯</span>
            <span className="meta-label">Predictive Target</span>
          </div>
          <div className="meta-value">P(Water | SAR)</div>
          <div className="meta-detail">Experimental candidate-water probability; calibration not established</div>
        </div>

        <div className="card meta-card">
          <div className="meta-card-header">
            <span className="meta-icon">🔒</span>
            <span className="meta-label">Model Integrity</span>
          </div>
          <div className="meta-value">Frozen Weights</div>
          <div className="meta-detail">Pre-trained artifact · Zero live retraining</div>
        </div>
      </div>

      {/* Main Attribution Display */}
      {loading ? (
        <div className="loading-state card">
          <div className="spinner" />
          <p>Loading Saabas tree attributions from API...</p>
        </div>
      ) : explanations ? (
        <div className="xai-main-content">
          <XaiPanel explanations={explanations} />
        </div>
      ) : (
        <div className="empty-state card">
          <p>No explanation data loaded for current campaign ({selectedRunId}).</p>
          <Link href="/explorer" className="btn btn-secondary">
            Return to Map Explorer
          </Link>
        </div>
      )}

      {/* SAR Physical Feature Dictionary */}
      <div className="card feature-glossary-card">
        <h3 className="card-title">Physical SAR Feature Interpretability Dictionary</h3>
        <p className="card-description">
          Synthetic Aperture Radar does not capture optical reflectance. Instead, microwaves interact with
          surface dielectric properties, surface roughness, and geometric structure.
        </p>

        <div className="feature-grid">
          <div className="feature-item">
            <div className="feature-tag">VV Backscatter (dB)</div>
            <p className="feature-exp">
              <strong>Specular Reflection:</strong> Calm open water acts as a specular mirror, reflecting microwave
              energy away from the satellite sensor and producing very low backscatter (typically &lt; -18 dB).
              Lower VV backscatter strongly drives positive water probability.
            </p>
          </div>

          <div className="feature-item">
            <div className="feature-tag">VH Backscatter (dB)</div>
            <p className="feature-exp">
              <strong>Volume &amp; Double-Bounce:</strong> Cross-polarization measures depolarized returns caused by
              volume scattering in vegetation or double-bounce from flooded structures/shrubs. Crucial for detecting
              flooded vegetation and agricultural fields.
            </p>
          </div>

          <div className="feature-item">
            <div className="feature-tag">Polarization Difference (VV - VH)</div>
            <p className="feature-exp">
              <strong>Roughness Discrimination:</strong> Difference metric separating wind-roughened open water
              from emergent vegetation and bare soil sandbars (chars).
            </p>
          </div>

          <div className="feature-item">
            <div className="feature-tag">Cross-Polarization Ratio</div>
            <p className="feature-exp">
              <strong>Depolarization Strength:</strong> Registered feature is the co-pol to cross-pol intensity ratio (VV / VH).
              Provides scale-independent dielectric discrimination for wet versus dry alluvium.
            </p>
          </div>

          <div className="feature-item">
            <div className="feature-tag">Spatial Texture GLCM (VV)</div>
            <p className="feature-exp">
              <strong>Homogeneity:</strong> Gray-Level Co-occurrence Matrix contrast. Continuous open water bodies
              exhibit near-zero spatial contrast, whereas riverbank boundaries show high texture gradients.
            </p>
          </div>

          <div className="feature-item">
            <div className="feature-tag">Spatial Texture GLCM (VH)</div>
            <p className="feature-exp">
              <strong>Structural Heterogeneity:</strong> Cross-polarized spatial contrast distinguishing braided
              channel bars, settlements, and embankments from uniform standing flood pools.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

