import React, { useState, useEffect } from 'react';
import { JamunaMap } from '../components/Map/JamunaMap';
import { ScientificSummary } from '../components/Summary/ScientificSummary';
import { LoadingState } from '../components/Common/LoadingState';
import { LoadedRun } from '../api/types';
import { Link, useRouter } from '../router/Router';

interface ExplorerPageProps {
  loadedRun: LoadedRun | null;
  activeLayer: string;
  onLayerChange: (layerId: string) => void;
  selectedRunId: string;
  onSelectRun: (runId: string) => void;
  isLoading?: boolean;
}

export const ExplorerPage: React.FC<ExplorerPageProps> = ({
  loadedRun,
  activeLayer,
  onLayerChange,
  selectedRunId,
  isLoading = false,
}) => {
  const { queryParams } = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    const layerParam = queryParams.get('layer');
    if (layerParam && layerParam !== activeLayer) {
      onLayerChange(layerParam);
    }
  }, [queryParams, activeLayer, onLayerChange]);

  if (isLoading || !loadedRun) {
    return (
      <div className="explorer-page-loading">
        <LoadingState message={`Loading SAR satellite observation workspace for ${selectedRunId}...`} />
      </div>
    );
  }

  const summary = loadedRun.summary;
  const manifest = loadedRun.manifest;
  const is2025 = selectedRunId === 'run_20261111_164348_f3c2b8';

  return (
    <div className="explorer-page">
      {/* Explorer Sub-Header Bar */}
      <div className="explorer-sub-header">
        <div className="explorer-title-group">
          <h2 className="page-heading">Satellite Map Explorer</h2>
          <span className="campaign-badge">
            {is2025 ? '2025 Live Observation' : '2024 Monsoon Baseline'}
          </span>
          <span className="reach-location-tag">Kazipur / Sirajganj Reach, Jamuna River</span>
        </div>

        <div className="explorer-actions">
          <Link to="/comparison" className="explorer-quick-link">
            ⚖️ Open Before/After Comparison
          </Link>
          <Link to="/explainable-ai" className="explorer-quick-link">
            🧠 Inspect XAI Model
          </Link>
          <button
            className="sidebar-toggle-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand metrics sidebar' : 'Collapse metrics sidebar'}
          >
            {sidebarCollapsed ? '◀ Show Metrics' : '▶ Hide Metrics'}
          </button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className={`explorer-workspace ${sidebarCollapsed ? 'sidebar-hidden' : ''}`}>
        {/* Main Map Column (takes majority of screen space) */}
        <div className="explorer-map-column">
          <JamunaMap
            runId={loadedRun.runId}
            manifest={manifest}
            summary={summary}
            activeLayer={activeLayer}
            onLayerChange={onLayerChange}
          />
        </div>

        {/* Right-Hand Scientific Summary Sidebar */}
        {!sidebarCollapsed && (
          <aside className="explorer-sidebar-column">
            <div className="sidebar-scroll-wrapper">
              <ScientificSummary summary={summary} />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};
