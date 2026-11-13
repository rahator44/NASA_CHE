import { useState, useEffect, useCallback, useRef } from 'react';
import { Header } from './components/Header/Header';
import { ErrorState } from './components/Common/ErrorState';
import {
  fetchRunSummary,
  fetchVisualManifest,
  fetchRunExplanations,
  fetchRegionAnalysisResults,
} from './api/client';
import { CampaignOption, LoadedRun } from './api/types';
import {
  DEFAULT_ANALYSIS_ID,
  assertPublishedRunIdentity,
  buildCampaignOptions,
  mergeDisplayedCampaigns,
  resolveSelectedAnalysisId,
} from './state/analysisSelection';
import { RouterProvider, useRouter } from './router/Router';
import { DashboardPage } from './pages/DashboardPage';
import { ExplorerPage } from './pages/ExplorerPage';
import { ComparisonPage } from './pages/ComparisonPage';
import { XaiPage } from './pages/XaiPage';
import { SciencePage } from './pages/SciencePage';
import { NewAnalysisPage } from './pages/NewAnalysisPage';
import { NotFoundPage } from './pages/NotFoundPage';
import './App.css';

function AppContent() {
  const { currentPath, queryParams, setQueryParam, replaceQueryParam } = useRouter();

  // The `run` query parameter is the only selected analysis id.
  const selectedRunId = resolveSelectedAnalysisId(queryParams.toString());
  const initialLayer = queryParams.get('layer') || 'transitions';

  const [activeLayer, setActiveLayer] = useState<string>(initialLayer);
  const [loadedRun, setLoadedRun] = useState<LoadedRun | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [errorRunId, setErrorRunId] = useState<string | null>(null);
  const [catalogue, setCatalogue] = useState<CampaignOption[]>([]);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  // Monotonic request generation token & AbortController to prevent race conditions
  const currentRequestId = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const loadRunData = useCallback(async (runId: string) => {
    const requestId = ++currentRequestId.current;

    // Abort previous in-flight requests immediately
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    setErrorRunId(null);
    setLoadedRun(null);

    try {
      // Parallel atomic fetch of summary, manifest, and explainability artifacts
      const [sumData, manData, xaiData] = await Promise.all([
        fetchRunSummary(runId, controller.signal),
        fetchVisualManifest(runId, controller.signal),
        fetchRunExplanations(runId, controller.signal).catch((e) => {
          console.warn(`Optional explanations fetch for ${runId} returned note:`, e);
          return undefined;
        }),
      ]);

      // Stale response rejection: if a newer request was dispatched, ignore this response
      if (requestId !== currentRequestId.current) {
        return;
      }

      assertPublishedRunIdentity(runId, sumData.run_id, manData.run_id);

      // Atomic state publication: summary, manifest, and explanations published together
      setLoadedRun({
        runId,
        summary: sumData,
        manifest: manData,
        explanations: xaiData,
      });

      // Reset active layer if the newly loaded run manifest doesn't support it
      const supportedLayers = manData.layers
        .filter((l) => Boolean(l.tile_url_template))
        .map((l) => l.layer_id);

      setActiveLayer((prev) => (supportedLayers.includes(prev) ? prev : 'transitions'));
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') {
        return;
      }
      if (requestId === currentRequestId.current) {
        console.error('Run loading failed:', err);
        setError(err instanceof Error ? err.message : 'Unknown error loading scientific observation data');
        setErrorRunId(runId);
        setLoadedRun(null);
      }
    } finally {
      if (requestId === currentRequestId.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!queryParams.get('run')) {
      replaceQueryParam('run', DEFAULT_ANALYSIS_ID);
    }
  }, [queryParams, replaceQueryParam]);

  useEffect(() => {
    loadRunData(selectedRunId);

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [selectedRunId, loadRunData]);

  useEffect(() => {
    const controller = new AbortController();
    fetchRegionAnalysisResults('jamuna_sirajganj', controller.signal)
      .then((records) => {
        setCatalogue(buildCampaignOptions(records));
        setCatalogueError(null);
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name === 'AbortError') return;
        setCatalogueError(err instanceof Error ? err.message : 'Failed to load analysis records');
      });
    return () => controller.abort();
  }, [selectedRunId]);

  const visibleRun = loadedRun?.runId === selectedRunId ? loadedRun : null;
  const displayError = error && errorRunId === selectedRunId ? error : null;
  const displayLoading = isLoading || (!visibleRun && !displayError);
  const campaigns = mergeDisplayedCampaigns(catalogue, selectedRunId, visibleRun);

  const handleSelectRun = (newRunId: string) => {
    if (!newRunId || newRunId === selectedRunId) return;
    setQueryParam('run', newRunId);
  };

  const handleLayerChange = (newLayer: string) => {
    setActiveLayer(newLayer);
    if (currentPath === '/explorer') {
      setQueryParam('layer', newLayer);
    }
  };

  useEffect(() => {
    if (currentPath !== '/explorer') return;
    const layer = queryParams.get('layer');
    if (layer) setActiveLayer(layer);
  }, [queryParams, currentPath]);

  const renderCurrentPage = () => {
    if (displayError && currentPath !== '/science' && currentPath !== '/new-analysis') {
      return (
        <ErrorState
          error={displayError}
          onRetry={() => loadRunData(selectedRunId)}
        />
      );
    }

    switch (currentPath) {
      case '/':
        return (
          <DashboardPage
            loadedRun={visibleRun}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
            isLoading={displayLoading}
          />
        );
      case '/explorer':
        return (
          <ExplorerPage
            loadedRun={visibleRun}
            activeLayer={activeLayer}
            onLayerChange={handleLayerChange}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
            isLoading={displayLoading}
          />
        );
      case '/comparison':
        return (
          <ComparisonPage
            loadedRun={visibleRun}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
            isLoading={displayLoading}
          />
        );
      case '/explainable-ai':
        return (
          <XaiPage
            explanations={visibleRun?.explanations || null}
            selectedRunId={selectedRunId}
            loading={displayLoading}
          />
        );
      case '/science':
        return <SciencePage />;
      case '/new-analysis':
        return <NewAnalysisPage />;
      default:
        return <NotFoundPage />;
    }
  };

  return (
    <div
      className="app-shell"
      data-active-analysis-id={selectedRunId}
      data-loaded-analysis-id={visibleRun?.runId || ''}
    >
      <Header
        selectedRunId={selectedRunId}
        campaigns={campaigns}
        catalogueError={catalogueError}
        onSelectRun={handleSelectRun}
        isLoading={displayLoading}
      />

      <main className={`main-content ${currentPath === '/explorer' ? 'no-scroll' : ''}`}>
        {renderCurrentPage()}
      </main>

      <footer className="app-footer">
        <div className="footer-content">
          <span className="footer-brand">NASA Space Apps Challenge 2026 — Dancing with the SARs</span>
          <span className="footer-separator">•</span>
          <span>Copernicus Sentinel-1 SAR Dual-Pol Calibration Engine</span>
          <span className="footer-separator">•</span>
          <span>Kazipur / Sirajganj Reach, Jamuna River, Bangladesh</span>
        </div>
      </footer>
    </div>
  );
}

export function App() {
  return (
    <RouterProvider>
      <AppContent />
    </RouterProvider>
  );
}

export default App;
