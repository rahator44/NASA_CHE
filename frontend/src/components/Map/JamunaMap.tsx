import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import { resolveTileUrl } from '../../api/client';
import { parseWktPolygon, boundsToPolygonCoords } from '../../utils/wkt';
import { Legend } from './Legend';
import { VisualManifest, RunSummary } from '../../api/types';

interface JamunaMapProps {
  runId: string;
  manifest: VisualManifest;
  summary: RunSummary;
  activeLayer: string;
  onLayerChange: (layerId: string) => void;
  standalone?: boolean;
}

type BasemapStyle = 'dark' | 'standard' | 'none';

export const JamunaMap: React.FC<JamunaMapProps> = ({
  runId,
  manifest,
  summary,
  activeLayer,
  onLayerChange,
  standalone = false,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const basemapLayerRef = useRef<L.TileLayer | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const aoiLayerRef = useRef<L.Polygon | null>(null);

  const [basemapStyle, setBasemapStyle] = useState<BasemapStyle>('dark');
  const [basemapStatus, setBasemapStatus] = useState<'loaded' | 'unavailable'>('loaded');
  const [overlayOpacity, setOverlayOpacity] = useState<number>(0.92);
  const [mouseCoords, setMouseCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [isControlsCollapsed, setIsControlsCollapsed] = useState<boolean>(false);
  const [isLayerDropdownOpen, setIsLayerDropdownOpen] = useState<boolean>(false);
  const layerDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        layerDropdownRef.current &&
        !layerDropdownRef.current.contains(event.target as Node)
      ) {
        setIsLayerDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Close dropdown on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsLayerDropdownOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  // Filter selectable raster layers that provide a valid tile URL template
  const selectableTileLayers = manifest.layers.filter(
    (layer) => typeof layer.tile_url_template === 'string' && layer.tile_url_template.trim().length > 0
  );

  const currentActiveLayer = manifest.layers.find((l) => l.layer_id === activeLayer);

  // Focus AOI helper
  const fitToAoi = useCallback(() => {
    const map = mapRef.current;
    const aoi = aoiLayerRef.current;
    if (map && aoi) {
      map.fitBounds(aoi.getBounds(), {
        padding: [20, 20],
        maxZoom: 14,
        animate: true,
      });
    }
  }, []);

  // 1. Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const bounds = manifest.geographic_bounds.epsg4326;
    const centerLat = manifest.geographic_bounds.center?.lat ?? (bounds[1] + bounds[3]) / 2;
    const centerLon = manifest.geographic_bounds.center?.lon ?? (bounds[0] + bounds[2]) / 2;

    const map = L.map(mapContainerRef.current, {
      center: [centerLat, centerLon],
      zoom: 13,
      minZoom: 6,
      maxZoom: 18,
      zoomControl: false, // We'll add custom positioned zoom control
    });

    // Custom positioned zoom control (top-left so top-right is reserved for modern layer dropdown)
    L.control.zoom({ position: 'topleft' }).addTo(map);

    // Metric scale bar (bottom-left)
    L.control.scale({ imperial: false, metric: true, position: 'bottomleft' }).addTo(map);

    // Track mouse coordinates
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      setMouseCoords({ lat: e.latlng.lat, lon: e.latlng.lng });
    });

    map.on('mouseout', () => {
      setMouseCoords(null);
    });

    mapRef.current = map;

    // Responsive resize observer
    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });
    if (mapContainerRef.current) {
      resizeObserver.observe(mapContainerRef.current);
    }

    const resizeTimer = setTimeout(() => {
      map.invalidateSize();
    }, 150);

    return () => {
      clearTimeout(resizeTimer);
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []); // Run once on mount

  // 2. Manage Basemap Layer (OpenStreetMap with clean fallback)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (basemapLayerRef.current) {
      map.removeLayer(basemapLayerRef.current);
      basemapLayerRef.current = null;
    }

    if (basemapStyle === 'none') {
      return;
    }

    // Legitimate, non-API-key OpenStreetMap raster tile service
    const osmUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    const tileClassName = basemapStyle === 'dark' ? 'osm-basemap-dark' : 'osm-basemap-standard';

    const basemap = L.tileLayer(osmUrl, {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
      maxZoom: 19,
      className: tileClassName,
    });

    basemap.on('tileload', () => {
      setBasemapStatus('loaded');
    });

    basemap.on('tileerror', (e: any) => {
      setBasemapStatus('unavailable');
      if (e?.tile) {
        e.tile.style.display = 'none';
        e.tile.classList.add('leaflet-tile-error');
      }
    });

    basemap.addTo(map);
    basemapLayerRef.current = basemap;
  }, [basemapStyle]);

  // 3. Update AOI Polygon & Fit Bounds
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (aoiLayerRef.current) {
      map.removeLayer(aoiLayerRef.current);
      aoiLayerRef.current = null;
    }

    let coords: [number, number][] = [];
    if (summary.study_aoi?.wkt) {
      coords = parseWktPolygon(summary.study_aoi.wkt);
    }
    if (coords.length === 0 && manifest.geographic_bounds?.epsg4326) {
      coords = boundsToPolygonCoords(manifest.geographic_bounds.epsg4326);
    }

    if (coords.length > 0) {
      const aoiPolygon = L.polygon(coords, {
        color: '#06b6d4',
        weight: 2.5,
        dashArray: '6, 6',
        fillColor: '#0891b2',
        fillOpacity: 0.05,
      }).addTo(map);

      aoiPolygon.bindTooltip(
        `Study AOI (${summary.study_aoi?.geometric_vector_area_km2?.toFixed(1) ?? 'area unavailable'}${summary.study_aoi?.geometric_vector_area_km2 != null ? ' km²' : ''})`,
        { permanent: false, direction: 'top', className: 'aoi-tooltip' }
      );

      aoiLayerRef.current = aoiPolygon;
      // Frame the study area with sensible maxZoom so it occupies adequate map space
      map.fitBounds(aoiPolygon.getBounds(), { padding: [20, 20], maxZoom: 14 });
      map.invalidateSize();
    }
  }, [summary.study_aoi, manifest.geographic_bounds]);

  // 4. Update Scientific SAR Tile Layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
      tileLayerRef.current = null;
    }

    const currentVisualLayer = manifest.layers.find((l) => l.layer_id === activeLayer);
    if (!currentVisualLayer?.tile_url_template) {
      return;
    }

    try {
      const tileUrl = resolveTileUrl(currentVisualLayer.tile_url_template);
      const newLayer = L.tileLayer(tileUrl, {
        opacity: overlayOpacity,
        maxZoom: 18,
        minZoom: 1,
        tileSize: 256,
        attribution: 'Sentinel-1 SAR / ESA SNAP / Earth Pulse',
        className: 'scientific-sar-tile',
      });

      newLayer.on('tileerror', (e: any) => {
        if (e?.tile) {
          e.tile.style.display = 'none';
        }
      });

      newLayer.addTo(map);
      tileLayerRef.current = newLayer;
    } catch (err) {
      console.error('Failed to attach scientific tile layer:', err);
    }
  }, [runId, activeLayer, manifest.layers, overlayOpacity]);

  return (
    <div className={`jamuna-map-wrapper ${standalone ? 'standalone-mode' : ''}`}>
      {/* Top Map Toolbar */}
      <div className="map-toolbar">
        <div className="toolbar-left">
          <button
            className="map-action-btn focus-aoi-btn btn-focus-aoi"
            onClick={fitToAoi}
            title="Focus Jamuna River study area"
          >
            🎯 Focus Study Area
          </button>

          <div className="basemap-selector" id="basemap-mode-select">
            <span className="control-label">Basemap:</span>
            <button
              className={`basemap-btn ${basemapStyle === 'dark' ? 'active' : ''}`}
              onClick={() => setBasemapStyle('dark')}
              title="OpenStreetMap Dark Contrast"
            >
              Dark
            </button>
            <button
              className={`basemap-btn ${basemapStyle === 'standard' ? 'active' : ''}`}
              onClick={() => setBasemapStyle('standard')}
              title="Standard OpenStreetMap"
            >
              OSM
            </button>
            <button
              className={`basemap-btn ${basemapStyle === 'none' ? 'active' : ''}`}
              onClick={() => setBasemapStyle('none')}
              title="Blank Canvas (Radar Only)"
            >
              Canvas
            </button>
          </div>

          {basemapStatus === 'unavailable' && basemapStyle !== 'none' && (
            <span className="basemap-fallback-badge" title="Basemap tile server unavailable. Scientific radar overlays remain fully operational.">
              ⚠️ Basemap Offline (Canvas Mode)
            </span>
          )}
        </div>

        <div className="toolbar-right">
          <div className="opacity-control">
            <span className="control-label">Radar Opacity:</span>
            <input
              type="range"
              min="0.3"
              max="1"
              step="0.05"
              value={overlayOpacity}
              onChange={(e) => setOverlayOpacity(parseFloat(e.target.value))}
              className="opacity-slider layer-slider"
              title={`Overlay opacity: ${Math.round(overlayOpacity * 100)}%`}
            />
            <span className="opacity-val">{Math.round(overlayOpacity * 100)}%</span>
          </div>

          <button
            className="map-action-btn collapse-toggle"
            onClick={() => setIsControlsCollapsed(!isControlsCollapsed)}
            title="Toggle map legend visibility"
          >
            {isControlsCollapsed ? '📊 Show Legend' : '✕ Hide Legend'}
          </button>
        </div>
      </div>

      {/* Main Leaflet Canvas */}
      <div className="map-canvas-container">
        <div ref={mapContainerRef} className="leaflet-map-canvas" id="jamuna-leaflet-map" />

        {/* Top-Right Modern Layer Selector Dropdown */}
        {!standalone && (
          <div className="map-layer-dropdown-wrapper" ref={layerDropdownRef}>
            <button
              type="button"
              className={`map-layer-dropdown-trigger ${isLayerDropdownOpen ? 'active' : ''}`}
              onClick={() => setIsLayerDropdownOpen((prev) => !prev)}
              aria-expanded={isLayerDropdownOpen}
              aria-haspopup="listbox"
              title="Select active satellite radar layer"
            >
              <span className="dropdown-trigger-icon">📡</span>
              <div className="dropdown-trigger-text">
                <span className="dropdown-trigger-label">Radar Product</span>
                <span className="dropdown-trigger-title">
                  {currentActiveLayer?.title || 'Select Layer'}
                </span>
              </div>
              <span className={`dropdown-trigger-chevron ${isLayerDropdownOpen ? 'open' : ''}`}>
                ▼
              </span>
            </button>

            <div
              className={`map-layer-dropdown-menu ${isLayerDropdownOpen ? 'open' : ''}`}
              role="listbox"
            >
              <div className="dropdown-menu-header">
                <div className="header-title-row">
                  <span className="header-icon">📡</span>
                  <span className="header-text">Satellite Radar Layers</span>
                </div>
                <span className="header-count-badge">
                  {selectableTileLayers.length} Layers
                </span>
              </div>

              <div className="dropdown-menu-list">
                {selectableTileLayers.map((layer) => {
                  const isSelected = activeLayer === layer.layer_id;
                  return (
                    <button
                      key={layer.layer_id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`layer-btn layer-dropdown-option ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        onLayerChange(layer.layer_id);
                        setIsLayerDropdownOpen(false);
                      }}
                      title={layer.title}
                    >
                      <div className="option-status-col">
                        <span className={`option-radio-dot ${isSelected ? 'active' : ''}`} />
                      </div>
                      <div className="option-content-col">
                        <span className="option-title layer-btn-title">{layer.title}</span>
                        <div className="option-meta-row">
                          <span className={`option-type-tag layer-btn-type ${layer.type.toLowerCase()}`}>
                            {layer.type.toUpperCase()}
                          </span>
                        </div>
                      </div>
                      {isSelected && (
                        <div className="option-check-col">
                          <span className="option-checkmark">✓</span>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Bottom-Left Floating Legend Dock */}
        {!standalone && !isControlsCollapsed && (
          <div className="map-legend-dock-floating">
            <Legend
              activeLayer={activeLayer}
              layer={currentActiveLayer}
              summary={summary}
            />
          </div>
        )}

        {/* Live Cursor Coordinates Overlay */}
        <div className="map-coordinates-bar map-coords-badge">
          <div className="aoi-footprint-badge">
            <span className="coord-dot"></span>
            AOI: Kazipur / Sirajganj (89.60°–89.68° E, 24.60°–24.68° N)
          </div>
          {mouseCoords ? (
            <div className="live-coords">
              Lat: {mouseCoords.lat.toFixed(4)}° N, Lon: {mouseCoords.lon.toFixed(4)}° E
            </div>
          ) : (
            <div className="live-coords subtle">Hover map for coordinates</div>
          )}
        </div>
      </div>
    </div>
  );
};
