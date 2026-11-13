import React from 'react';
import { Link } from '../router/Router';

export const SciencePage: React.FC = () => {
  return (
    <div className="page-container science-page">
      <div className="page-header science-page-header">
        <div className="page-header-text">
          <div className="badge-row">
            <span className="badge badge-cyan">NASA Space Apps Challenge 2026</span>
            <span className="badge badge-purple">Dancing with the SARs</span>
            <span className="badge badge-green">Experimental Research Platform</span>
          </div>
          <h1 className="page-title">Scientific Principles &amp; Processing Pipeline</h1>
          <p className="page-subtitle">
            Rigorous radar remote sensing, hydro-morphodynamic transects, and explainable machine learning
            applied to the braided Jamuna River corridor, Bangladesh.
          </p>
        </div>
        <div className="page-header-actions">
          <Link href="/explorer" className="btn btn-primary action-btn">
            🛰️ Open Satellite Map Explorer
          </Link>
        </div>
      </div>

      {/* Grid of Core Pillars */}
      <div className="science-pillar-grid">
        <div className="card science-card">
          <div className="card-badge">Pillar 1</div>
          <h2 className="science-card-title">📡 C-Band SAR Microwave Physics</h2>
          <p>
            Earth Pulse utilizes active microwave radar data acquired by the Copernicus Sentinel-1 satellite constellation.
            Operating at C-band (central frequency 5.405 GHz, wavelength λ ≈ 5.55 cm), synthetic aperture radar penetrates
            clouds, rain, and monsoonal atmospheric moisture, enabling all-weather, day-and-night observation of inundation dynamics.
          </p>
          <div className="science-callout">
            <strong>Polarimetric Interaction:</strong>
            <ul>
              <li>
                <strong>VV (Vertical-transmit, Vertical-receive):</strong> Highly sensitive to surface roughness. Smooth standing water acts as a specular mirror, reflecting microwave pulses away from the antenna and creating dark pixels (typically &lt; -18 dB).
              </li>
              <li>
                <strong>VH (Vertical-transmit, Horizontal-receive):</strong> Sensitive to volume scattering and depolarization within emergent vegetation, crops, and canopy structures. Crucial for detecting inundated vegetation.
              </li>
            </ul>
          </div>
        </div>

        <div className="card science-card">
          <div className="card-badge">Pillar 2</div>
          <h2 className="science-card-title">⚙️ ESA SNAP Calibration &amp; Preprocessing</h2>
          <p>
            Raw Level-1 Ground Range Detected (GRD) products undergo rigorous radiometric calibration and geometric terrain correction:
          </p>
          <ol className="pipeline-steps">
            <li><strong>Orbit State Vector Application:</strong> The graph requests Sentinel Precise orbit files with automatic download and permits continuation if unavailable; achieved orbit accuracy is not asserted here.</li>
            <li>
              <strong>Radiometric Calibration:</strong> Converting raw digital numbers (DN) to radar backscatter coefficient (sigma nought, σ° in decibels):
              <code>σ° (dB) = 10 · log10(DN² / A²)</code>
            </li>
            <li>
              <strong>Speckle Noise Filtering:</strong> The dynamic workflow applies a Lee 5×5 filter to the calibrated backscatter. Filtering reduces speckle but can also affect edge detail.
            </li>
            <li>
              <strong>Terrain Correction &amp; Geocoding:</strong> The archived Jamuna graph uses the Copernicus 30 m Global DEM, a 20 m output pixel spacing, and EPSG:32645. That CRS is specific to the Bangladesh demonstration and is not suitable for unrelated locations.
            </li>
          </ol>
        </div>

        <div className="card science-card">
          <div className="card-badge">Pillar 3</div>
          <h2 className="science-card-title">🌊 Hydrological Transition Accounting</h2>
          <p>
            Flood dynamics are quantified through rigorous dual-epoch pixel transition matrices between baseline epoch T1
            and post-event observation epoch T2:
          </p>
          <div className="transition-math-block">
            <div className="math-row">
              <span className="formula-label">Candidate Inundation:</span>
              <code>A_inundated = transition pixel count × pixel ground area from the raster transform</code>
            </div>
            <div className="math-row">
              <span className="formula-label">Receded / Absorbed:</span>
              <code>A_receded = transition pixel count × pixel ground area from the raster transform</code>
            </div>
            <div className="math-row">
              <span className="formula-label">Net Candidate Change:</span>
              <code>ΔA_net = A_inundated - A_receded</code>
            </div>
          </div>
          <p className="footnote-text">
            For 2024 Monsoon Baseline: +5.8432 km² net water change.<br />
            For January 2025 Live SAR Run: +1.0440 km² net candidate water change.
          </p>
        </div>

        <div className="card science-card">
          <div className="card-badge">Pillar 4</div>
          <h2 className="science-card-title">📏 Riverbank Morphodynamics Gating</h2>
          <p>
            The Jamuna River is one of the most dynamic braided river systems on Earth, migrating hundreds of meters annually.
            The archived Jamuna processing uses regularly spaced cross-sections (36 were evaluated in each shipped campaign). These are candidate channel-margin measurements and do not by themselves establish permanent erosion or accretion:
          </p>
          <ul className="transect-features">
            <li>
              <strong>Transect Spacing:</strong> The current analyzer defaults to 250 m spacing; it derives transects from the input raster grid. The shipped Jamuna transects must not be reused for another AOI.
            </li>
            <li>
              <strong>Quality Gating:</strong> The 2025 campaign applies channel-correspondence checks and excludes one of 36 transects. The 2024 campaign is legacy output without that calibrated correspondence gate.
            </li>
            <li>
              <strong>Interpretation:</strong> No in-situ bankline or hydrometric ground truth is supplied by these measurements. Waterline movement can reflect water-level and classification changes as well as channel movement.
            </li>
          </ul>
        </div>

        <div className="card science-card">
          <div className="card-badge">Pillar 5</div>
          <h2 className="science-card-title">🤖 Explainable AI &amp; Exact Saabas Additivity</h2>
          <p>
            The frozen 40-tree Random Forest (maximum depth 6, minimum leaf size 10) is an experimental candidate-probability layer. Its registry is limited to the Jamuna training region; the primary operational water baseline remains adaptive Lee 5×5 dual-polarization Otsu.
          </p>
          <div className="science-callout">
            <strong>Mathematical Conservation:</strong>
            <p>
              Feature attributions are calculated using the exact tree-path decomposition of Saabas (2014):
            </p>
            <code>f(x) = E[f(x)] + Σ_i φ_i(x)</code>
            <p className="mt-2">
              For reported samples, the sum of feature attributions φ_i plus the reference value reconstructs the model output within numerical tolerance. This additivity property does not measure predictive accuracy; the archived audit reports residuals at approximately 10⁻⁸ for its checked cases.
            </p>
          </div>
        </div>

        <div className="card science-card">
          <div className="card-badge">Pillar 6</div>
          <h2 className="science-card-title">📚 Data Provenance &amp; Attribution</h2>
          <p>
            Earth Pulse acknowledges the vital satellite data providers and scientific open-source frameworks:
          </p>
          <ul className="citation-list">
            <li>
              <strong>European Space Agency (ESA):</strong> Copernicus Sentinel-1 Synthetic Aperture Radar Level-1 GRD products distributed under the Copernicus Open Access License.
            </li>
            <li>
              <strong>NASA / ASF DAAC:</strong> Alaska Satellite Facility Distributed Active Archive Center for Sentinel-1 radar data archiving and distribution.
            </li>
            <li>
              <strong>SRTM:</strong> NASA Shuttle Radar Topography Mission 1 Arc-Second Global Elevation Model (30 m).
            </li>
            <li>
              <strong>OpenStreetMap:</strong> Basemap tiles © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors, licensed under ODbL.
            </li>
          </ul>
        </div>
      </div>

      {/* Get Earth Pulse: Download & Deployment Portal */}
      <div className="card download-setup-card">
        <div className="download-setup-header">
          <div className="badge-row">
            <span className="badge badge-cyan">Reproducible Packaging</span>
            <span className="badge badge-purple">GitHub Release Asset</span>
            <span className="badge badge-green">Linux x86_64 Ready</span>
          </div>
          <h2 className="download-setup-title">📦 Get Earth Pulse: Download &amp; Local Setup</h2>
          <p className="download-setup-subtitle">
            Deploy Earth Pulse locally on your workstation. Explore verified historical campaigns in safe demo mode,
            or connect your own NASA Earthdata and ESA SNAP installation for dynamic SAR acquisitions.
          </p>
        </div>

        <div className="download-action-row">
          <a
            href="https://github.com/rahator44/NASA_CHE"
            target="_blank"
            rel="noreferrer"
            className="btn btn-primary"
          >
            🐙 GitHub Source Repository
          </a>
          <a
            href="https://github.com/rahator44/NASA_CHE/releases"
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary"
          >
            💾 Download Portable Demo Data (.zip)
          </a>
          <Link href="/explorer" className="btn btn-outline">
            🗺️ Explore Live Web Demo
          </Link>
        </div>

        <div className="setup-guides-grid">
          <div className="setup-guide-box">
            <div className="guide-header">
              <span className="guide-icon">🐧</span>
              <h4 className="guide-title">1. Linux Installation</h4>
            </div>
            <p className="guide-text">
              Tested on Kali GNU/Linux Rolling, Ubuntu 22.04/24.04, and Debian 12 (x86_64).
            </p>
            <pre className="code-snippet">
              <code>{`# 1. Check prerequisites
bash scripts/check_prerequisites.sh

# 2. Automated setup (venv, deps, build)
bash scripts/install_linux.sh

# 3. Launch unified server (http://127.0.0.1:8000)
bash scripts/run_linux.sh`}</code>
            </pre>
          </div>

          <div className="setup-guide-box">
            <div className="guide-header">
              <span className="guide-icon">🛰️</span>
              <h4 className="guide-title">2. NASA Earthdata Setup</h4>
            </div>
            <p className="guide-text">
              <strong>Optional for demo mode.</strong> Required only for raw Sentinel-1 GRD downloads via ASF DAAC.
            </p>
            <ol className="guide-steps">
              <li>Register free account at <a href="https://urs.earthdata.nasa.gov" target="_blank" rel="noreferrer">urs.earthdata.nasa.gov</a></li>
              <li>Authorize <em>Alaska Satellite Facility DAAC</em></li>
              <li>Add credentials to <code>~/.netrc</code> with permissions <code>0600</code>:
                <pre className="code-snippet">
                  <code>{`machine urs.earthdata.nasa.gov
  login YOUR_USERNAME
  password YOUR_PASSWORD`}</code>
                </pre>
              </li>
            </ol>
          </div>

          <div className="setup-guide-box">
            <div className="guide-header">
              <span className="guide-icon">⚙️</span>
              <h4 className="guide-title">3. ESA SNAP 14.0.0 Configuration</h4>
            </div>
            <p className="guide-text">
              <strong>Optional for demo mode.</strong> Required only for executing new calibration &amp; terrain correction pipelines.
            </p>
            <ol className="guide-steps">
              <li>Download SNAP from <a href="https://step.esa.int/main/download/snap-download/" target="_blank" rel="noreferrer">step.esa.int</a></li>
              <li>Install the Sentinel-1 Toolbox</li>
              <li>Configure the GPT executable path:
                <pre className="code-snippet">
                  <code>{`export SNAP_GPT_PATH=/path/to/snap/bin/gpt`}</code>
                </pre>
              </li>
              <li>Required operators: <code>Apply-Orbit-File</code>, <code>ThermalNoiseRemoval</code>, <code>Calibration</code>, <code>Speckle-Filter</code>, <code>Terrain-Correction</code>.</li>
            </ol>
          </div>
        </div>
      </div>

      {/* Scientific Limitation and Peer-Review Caveats */}
      <div className="card warning-card science-disclaimer-card">
        <div className="warning-icon">⚠️</div>
        <div className="warning-content">
          <h4 className="warning-title">Scientific Scope &amp; Peer-Review Disclaimer</h4>
          <p>
            Earth Pulse is an advanced research and engineering demonstration created for the NASA Space Apps Challenge 2026
            ("Dancing with the SARs"). While the preprocessing, speckle filtering, thresholding, and XAI mathematical formulations
            follow established peer-reviewed radar hydrology standards, this platform is an experimental analysis tool and not an
            officially certified operational disaster dispatch system. Field teams must cross-verify satellite alerts with local hydrometric
            gauges and emergency management authorities (FFWC Bangladesh / BWDB).
          </p>
        </div>
      </div>
    </div>
  );
};

