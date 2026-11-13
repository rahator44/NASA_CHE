import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import {
  parseWktPolygon,
  polygonToWkt,
  validateAoiGeometry,
  DEMO_STUDY_AOI_WKT,
  JAMUNA_STUDY_REGION_WKT,
} from '../../utils/wkt';
import { GeometryValidationResult } from '../../api/types';

interface AoiDrawingMapProps {
  aoiWkt: string;
  onAoiChange: (wkt: string, validation: GeometryValidationResult) => void;
  validation: GeometryValidationResult;
}

export type DrawMode = 'none' | 'rectangle' | 'polygon';

export const AoiDrawingMap: React.FC<AoiDrawingMapProps> = ({
  aoiWkt,
  onAoiChange,
  validation,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  // Drawing state
  const [drawMode, setDrawMode] = useState<DrawMode>('none');
  const drawModeRef = useRef<DrawMode>('none');
  const [polygonPoints, setPolygonPoints] = useState<[number, number][]>([]);
  const polygonPointsRef = useRef<[number, number][]>([]);
  const [mouseCoords, setMouseCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [copiedWkt, setCopiedWkt] = useState<boolean>(false);

  // Layers & Markers
  const activePolygonLayerRef = useRef<L.Polygon | null>(null);
  const editHandlesLayerRef = useRef<L.LayerGroup | null>(null);
  const tempDrawLayerRef = useRef<L.LayerGroup | null>(null);
  const tempRectLayerRef = useRef<L.Rectangle | null>(null);
  const rectStartRef = useRef<L.LatLng | null>(null);
  const isMouseDownRef = useRef<boolean>(false);

  // Basemap style state
  const [basemapStyle, setBasemapStyle] = useState<'dark' | 'standard'>('dark');

  // Keep drawModeRef in sync
  useEffect(() => {
    drawModeRef.current = drawMode;
    const map = mapInstanceRef.current;
    if (!map) return;

    if (drawMode !== 'none') {
      map.getContainer().style.cursor = 'crosshair';
      // Disable map panning in rectangle drag-to-draw mode
      if (drawMode === 'rectangle') {
        map.dragging.disable();
      } else {
        map.dragging.enable();
      }
    } else {
      map.getContainer().style.cursor = '';
      map.dragging.enable();
    }
  }, [drawMode]);

  // Synchronize WKT update and validation callback
  const updateAoiFromLatLngs = useCallback(
    (latLngs: [number, number][]) => {
      const wkt = polygonToWkt(latLngs);
      const val = validateAoiGeometry(latLngs);
      onAoiChange(wkt, val);
    },
    [onAoiChange]
  );

  // Render AOI and attach draggable vertex handles, midpoint insertion handles, and move handle
  const renderAoiOnMap = useCallback(
    (wkt: string) => {
      const map = mapInstanceRef.current;
      if (!map) return;

      // Clean existing polygon and handles
      if (activePolygonLayerRef.current) {
        map.removeLayer(activePolygonLayerRef.current);
        activePolygonLayerRef.current = null;
      }
      if (editHandlesLayerRef.current) {
        editHandlesLayerRef.current.clearLayers();
      }

      if (!wkt) return;

      const latLngs = parseWktPolygon(wkt);
      if (latLngs.length < 3) return;

      // Primary AOI polygon
      const poly = L.polygon(latLngs, {
        color: '#38bdf8',
        weight: 3,
        fillColor: '#0284c7',
        fillOpacity: 0.25,
        className: 'active-user-aoi-polygon',
      }).addTo(map);
      activePolygonLayerRef.current = poly;

      // Layer group for interactive handles
      const handlesGroup = editHandlesLayerRef.current || L.layerGroup().addTo(map);
      editHandlesLayerRef.current = handlesGroup;
      handlesGroup.clearLayers();

      // Number of unique vertices (ignoring duplicate closing point if present)
      const isClosed =
        latLngs.length > 3 &&
        Math.abs(latLngs[0][0] - latLngs[latLngs.length - 1][0]) < 1e-7 &&
        Math.abs(latLngs[0][1] - latLngs[latLngs.length - 1][1]) < 1e-7;
      const uniqueCount = isClosed ? latLngs.length - 1 : latLngs.length;

      // 1. Draggable Vertex Handles
      for (let i = 0; i < uniqueCount; i++) {
        const [vLat, vLon] = latLngs[i];
        const vertexIcon = L.divIcon({
          className: 'aoi-vertex-marker-wrapper',
          html: '<div class="aoi-vertex-marker" title="Drag to reshape. Click to delete."></div>',
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        });

        const vertexMarker = L.marker([vLat, vLon], {
          draggable: true,
          icon: vertexIcon,
          zIndexOffset: 1000,
        });

        vertexMarker.on('drag', (e) => {
          const currentPoints = (poly.getLatLngs() as any)[0] as L.LatLng[];
          const updated: [number, number][] = currentPoints.map((pt) => [pt.lat, pt.lng]);
          const newPos = (e.target as L.Marker).getLatLng();
          updated[i] = [newPos.lat, newPos.lng];
          if (isClosed && i === 0) {
            updated[updated.length - 1] = [newPos.lat, newPos.lng];
          }
          poly.setLatLngs(updated as any);
        });

        vertexMarker.on('dragend', (e) => {
          const currentPoints = (poly.getLatLngs() as any)[0] as L.LatLng[];
          const updated: [number, number][] = currentPoints.map((pt) => [pt.lat, pt.lng]);
          const newPos = (e.target as L.Marker).getLatLng();
          updated[i] = [newPos.lat, newPos.lng];
          if (isClosed && i === 0) {
            updated[updated.length - 1] = [newPos.lat, newPos.lng];
          }
          updateAoiFromLatLngs(updated);
        });

        // Click on vertex to delete (only if more than 3 vertices remain)
        vertexMarker.on('click', () => {
          if (uniqueCount > 3) {
            const currentPoints = (poly.getLatLngs() as any)[0] as L.LatLng[];
            const updated: [number, number][] = currentPoints.map((pt) => [pt.lat, pt.lng]);
            updated.splice(i, 1);
            // Ensure closed loop
            if (updated.length >= 3) {
              updated[updated.length - 1] = updated[0];
            }
            updateAoiFromLatLngs(updated);
          }
        });

        handlesGroup.addLayer(vertexMarker);
      }

      // 2. Midpoint Insertion Handles
      for (let i = 0; i < uniqueCount; i++) {
        const nextIdx = (i + 1) % uniqueCount;
        const [lat1, lon1] = latLngs[i];
        const [lat2, lon2] = latLngs[nextIdx];
        const midLat = (lat1 + lat2) / 2;
        const midLon = (lon1 + lon2) / 2;

        const midpointIcon = L.divIcon({
          className: 'aoi-midpoint-marker-wrapper',
          html: '<div class="aoi-midpoint-marker" title="Click to insert vertex"></div>',
          iconSize: [10, 10],
          iconAnchor: [5, 5],
        });

        const midMarker = L.marker([midLat, midLon], {
          icon: midpointIcon,
          zIndexOffset: 500,
        });

        midMarker.on('click', () => {
          const currentPoints = (poly.getLatLngs() as any)[0] as L.LatLng[];
          const updated: [number, number][] = currentPoints.map((pt) => [pt.lat, pt.lng]);
          // Insert new point between i and i+1
          updated.splice(i + 1, 0, [midLat, midLon]);
          if (isClosed) {
            updated[updated.length - 1] = updated[0];
          }
          updateAoiFromLatLngs(updated);
        });

        handlesGroup.addLayer(midMarker);
      }

      // 3. Centroid Move Handle for full AOI translation
      const bounds = poly.getBounds();
      const center = bounds.getCenter();
      const moveIcon = L.divIcon({
        className: 'aoi-move-marker-wrapper',
        html: '<div class="aoi-move-marker" title="Drag to move entire AOI">✥</div>',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });

      const moveMarker = L.marker([center.lat, center.lng], {
        draggable: true,
        icon: moveIcon,
        zIndexOffset: 2000,
      });

      let startCenter: L.LatLng | null = null;
      let startCoords: [number, number][] = [];

      moveMarker.on('dragstart', (e) => {
        startCenter = (e.target as L.Marker).getLatLng();
        const currentPoints = (poly.getLatLngs() as any)[0] as L.LatLng[];
        startCoords = currentPoints.map((pt) => [pt.lat, pt.lng]);
      });

      moveMarker.on('drag', (e) => {
        if (!startCenter || startCoords.length === 0) return;
        const currentCenter = (e.target as L.Marker).getLatLng();
        const deltaLat = currentCenter.lat - startCenter.lat;
        const deltaLon = currentCenter.lng - startCenter.lng;
        const movedCoords: [number, number][] = startCoords.map(([lat, lon]) => [
          lat + deltaLat,
          lon + deltaLon,
        ]);
        poly.setLatLngs(movedCoords as any);
      });

      moveMarker.on('dragend', (e) => {
        if (!startCenter || startCoords.length === 0) return;
        const currentCenter = (e.target as L.Marker).getLatLng();
        const deltaLat = currentCenter.lat - startCenter.lat;
        const deltaLon = currentCenter.lng - startCenter.lng;
        const movedCoords: [number, number][] = startCoords.map(([lat, lon]) => [
          lat + deltaLat,
          lon + deltaLon,
        ]);
        updateAoiFromLatLngs(movedCoords);
      });

      handlesGroup.addLayer(moveMarker);
    },
    [updateAoiFromLatLngs]
  );

  // Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return;

    // Center on braided Jamuna River corridor (Sirajganj Reach)
    const map = L.map(mapContainerRef.current, {
      center: [24.64, 89.64],
      zoom: 11,
      minZoom: 8,
      maxZoom: 17,
      zoomControl: true,
      attributionControl: false,
    });
    mapInstanceRef.current = map;

    // Base OSM tiles
    const tileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      className: basemapStyle === 'dark' ? 'osm-basemap-dark' : 'osm-basemap-standard',
    });
    tileLayer.addTo(map);
    tileLayerRef.current = tileLayer;

    // Setup handle and temp layers
    const editGroup = L.layerGroup().addTo(map);
    editHandlesLayerRef.current = editGroup;

    const tempGroup = L.layerGroup().addTo(map);
    tempDrawLayerRef.current = tempGroup;

    // Reference corridor of supported Jamuna processing region
    const regionCoords = parseWktPolygon(JAMUNA_STUDY_REGION_WKT);
    if (regionCoords.length > 0) {
      const regionPoly = L.polygon(regionCoords, {
        color: '#6366f1',
        weight: 1.5,
        dashArray: '6, 6',
        fillOpacity: 0.02,
        fillColor: '#6366f1',
        interactive: true,
      });
      regionPoly.bindTooltip('Supported Jamuna River Processing Corridor (89.0°–90.5° E, 24.0°–25.5° N)', {
        sticky: true,
      });
      regionPoly.addTo(map);
    }

    // Reference demonstration AOI outline
    const demoCoords = parseWktPolygon(DEMO_STUDY_AOI_WKT);
    if (demoCoords.length > 0) {
      const demoPoly = L.polygon(demoCoords, {
        color: '#f59e0b',
        weight: 1.5,
        dashArray: '4, 4',
        fillOpacity: 0.04,
        fillColor: '#f59e0b',
        interactive: true,
      });
      demoPoly.bindTooltip('Demonstration Study Area (8.8 × 8.8 km Kazipur / Sirajganj Reach)', {
        sticky: true,
      });
      demoPoly.addTo(map);
    }

    // Scale control
    L.control.scale({ imperial: false, metric: true, position: 'bottomleft' }).addTo(map);

    // Mouse coordinates tracker & live drawing rubberband
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      setMouseCoords({ lat: e.latlng.lat, lon: e.latlng.lng });

      // Live drag-to-draw rectangle update
      if (drawModeRef.current === 'rectangle' && isMouseDownRef.current && rectStartRef.current) {
        const bounds = L.latLngBounds(rectStartRef.current, e.latlng);
        if (tempRectLayerRef.current) {
          tempRectLayerRef.current.setBounds(bounds);
        } else {
          tempRectLayerRef.current = L.rectangle(bounds, {
            color: '#38bdf8',
            weight: 2,
            dashArray: '4, 4',
            fillColor: '#0284c7',
            fillOpacity: 0.2,
          }).addTo(map);
        }
        return;
      }

      // Live rubberband for polygon drawing
      if (drawModeRef.current === 'polygon' && polygonPointsRef.current.length > 0) {
        if (tempDrawLayerRef.current) {
          tempDrawLayerRef.current.clearLayers();
          const points = polygonPointsRef.current;
          const rubberbandCoords: [number, number][] = [...points, [e.latlng.lat, e.latlng.lng]];
          const line = L.polyline(rubberbandCoords, {
            color: '#38bdf8',
            weight: 2,
            dashArray: '4, 4',
          });
          tempDrawLayerRef.current.addLayer(line);

          // Draw vertex dots for each clicked point
          points.forEach(([pLat, pLon]) => {
            const marker = L.circleMarker([pLat, pLon], {
              radius: 4,
              color: '#ffffff',
              fillColor: '#38bdf8',
              fillOpacity: 1,
              weight: 2,
            });
            tempDrawLayerRef.current?.addLayer(marker);
          });
        }
      }
    });

    // Mousedown: Used for intuitive drag-to-draw rectangle
    map.on('mousedown', (e: L.LeafletMouseEvent) => {
      if (drawModeRef.current !== 'rectangle') return;
      isMouseDownRef.current = true;
      rectStartRef.current = e.latlng;
      if (tempRectLayerRef.current) {
        map.removeLayer(tempRectLayerRef.current);
        tempRectLayerRef.current = null;
      }
    });

    // Mouseup: Completes drag-to-draw rectangle
    map.on('mouseup', (e: L.LeafletMouseEvent) => {
      if (drawModeRef.current !== 'rectangle' || !isMouseDownRef.current || !rectStartRef.current) return;
      isMouseDownRef.current = false;
      const start = rectStartRef.current;
      const end = e.latlng;
      rectStartRef.current = null;

      if (tempRectLayerRef.current) {
        map.removeLayer(tempRectLayerRef.current);
        tempRectLayerRef.current = null;
      }

      // Check for minimal size to avoid accidental clicks
      const minLatDelta = Math.abs(start.lat - end.lat);
      const minLonDelta = Math.abs(start.lng - end.lng);
      if (minLatDelta > 0.001 && minLonDelta > 0.001) {
        const minLat = Math.min(start.lat, end.lat);
        const maxLat = Math.max(start.lat, end.lat);
        const minLon = Math.min(start.lng, end.lng);
        const maxLon = Math.max(start.lng, end.lng);

        const rectCoords: [number, number][] = [
          [minLat, minLon],
          [minLat, maxLon],
          [maxLat, maxLon],
          [maxLat, minLon],
          [minLat, minLon],
        ];

        setDrawMode('none');
        updateAoiFromLatLngs(rectCoords);
      }
    });

    // Map click: Used for irregular polygon drawing
    map.on('click', (e: L.LeafletMouseEvent) => {
      const mode = drawModeRef.current;
      if (mode !== 'polygon') return;

      const clickLat = e.latlng.lat;
      const clickLon = e.latlng.lng;
      const updated = [...polygonPointsRef.current, [clickLat, clickLon] as [number, number]];
      polygonPointsRef.current = updated;
      setPolygonPoints(updated);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [updateAoiFromLatLngs, basemapStyle]);

  // Synchronize active AOI visual with controlled wkt
  useEffect(() => {
    renderAoiOnMap(aoiWkt);
  }, [aoiWkt, renderAoiOnMap]);

  // Basemap style switcher
  const handleBasemapChange = (style: 'dark' | 'standard') => {
    setBasemapStyle(style);
    if (tileLayerRef.current) {
      const el = tileLayerRef.current.getContainer();
      if (el) {
        el.className = `leaflet-layer ${style === 'dark' ? 'osm-basemap-dark' : 'osm-basemap-standard'}`;
      }
    }
  };

  // Complete polygon drawing
  const handleCompletePolygon = () => {
    const points = polygonPointsRef.current;
    if (points.length >= 3) {
      const closed = [...points, points[0]];
      updateAoiFromLatLngs(closed);
    }
    if (tempDrawLayerRef.current) {
      tempDrawLayerRef.current.clearLayers();
    }
    setDrawMode('none');
    polygonPointsRef.current = [];
    setPolygonPoints([]);
  };

  // Undo last vertex during polygon drawing
  const handleUndoVertex = () => {
    if (polygonPointsRef.current.length > 0) {
      const updated = polygonPointsRef.current.slice(0, -1);
      polygonPointsRef.current = updated;
      setPolygonPoints(updated);
      if (tempDrawLayerRef.current) {
        tempDrawLayerRef.current.clearLayers();
      }
    }
  };

  // Cancel drawing without changing current AOI
  const handleCancelDrawing = () => {
    setDrawMode('none');
    polygonPointsRef.current = [];
    setPolygonPoints([]);
    if (tempDrawLayerRef.current) {
      tempDrawLayerRef.current.clearLayers();
    }
    if (tempRectLayerRef.current && mapInstanceRef.current) {
      mapInstanceRef.current.removeLayer(tempRectLayerRef.current);
      tempRectLayerRef.current = null;
    }
  };

  // Shortcut: Use verified demonstration AOI
  const handleUseDemoAoi = () => {
    handleCancelDrawing();
    const coords = parseWktPolygon(DEMO_STUDY_AOI_WKT);
    updateAoiFromLatLngs(coords);

    if (mapInstanceRef.current && coords.length > 0) {
      const bounds = L.latLngBounds(coords.map(([lat, lon]) => [lat, lon]));
      mapInstanceRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 13 });
    }
  };

  // Clear AOI completely
  const handleClearAoi = () => {
    handleCancelDrawing();
    if (activePolygonLayerRef.current && mapInstanceRef.current) {
      mapInstanceRef.current.removeLayer(activePolygonLayerRef.current);
      activePolygonLayerRef.current = null;
    }
    if (editHandlesLayerRef.current) {
      editHandlesLayerRef.current.clearLayers();
    }
    onAoiChange('', {
      isValid: false,
      areaKm2: 0,
      vertexCount: 0,
      isContainedInStudyRegion: false,
      error: 'Area cleared. Select an area of interest on the map.',
    });
  };

  // Zoom camera to current AOI
  const handleFitAoi = () => {
    if (!mapInstanceRef.current || !aoiWkt) return;
    const coords = parseWktPolygon(aoiWkt);
    if (coords.length > 0) {
      const bounds = L.latLngBounds(coords.map(([lat, lon]) => [lat, lon]));
      mapInstanceRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
    }
  };

  // Export AOI as standard GeoJSON Polygon in WGS84 EPSG:4326
  const handleExportGeoJson = () => {
    if (!aoiWkt) return;
    const latLngs = parseWktPolygon(aoiWkt);
    if (latLngs.length < 3) return;

    // GeoJSON coordinates standard: [longitude, latitude]
    const coordinates = latLngs.map(([lat, lon]) => [lon, lat]);
    const geojson = {
      type: 'FeatureCollection',
      crs: {
        type: 'name',
        properties: { name: 'urn:ogc:def:crs:OGC:1.3:CRS84' },
      },
      features: [
        {
          type: 'Feature',
          properties: {
            name: 'Earth Pulse Study Area of Interest',
            area_km2: validation.areaKm2,
            is_jamuna_corridor: validation.isContainedInStudyRegion,
            created_at: new Date().toISOString(),
          },
          geometry: {
            type: 'Polygon',
            coordinates: [coordinates],
          },
        },
      ],
    };

    const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `earth_pulse_aoi_${Date.now()}.geojson`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Copy WKT string to clipboard
  const handleCopyWkt = async () => {
    if (!aoiWkt) return;
    try {
      await navigator.clipboard.writeText(aoiWkt);
      setCopiedWkt(true);
      setTimeout(() => setCopiedWkt(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div className="aoi-map-wrapper">
      {/* Top Map Toolbar */}
      <div className="aoi-map-toolbar">
        <div className="drawing-tools-group">
          <span className="toolbar-section-label">✏️ Area Selection:</span>

          {drawMode === 'none' ? (
            <>
              <button
                type="button"
                className="tool-btn btn-draw-box"
                onClick={() => setDrawMode('rectangle')}
                title="Click and drag on the map to draw a rectangular study area"
              >
                🔲 Draw Box
              </button>

              <button
                type="button"
                className="tool-btn btn-draw-poly"
                onClick={() => setDrawMode('polygon')}
                title="Click multiple points along river to outline a custom polygon"
              >
                📐 Draw Polygon
              </button>

              <button
                type="button"
                className="tool-btn btn-demo-shortcut btn-preset-aoi"
                onClick={handleUseDemoAoi}
                title="Load the verified Kazipur reach demonstration polygon (8.8 × 8.8 km)"
              >
                🎯 Use Demo Reach
              </button>
            </>
          ) : (
            <>
              {drawMode === 'polygon' && (
                <>
                  <button
                    type="button"
                    className="tool-btn btn-finish-polygon btn-finish-poly"
                    onClick={handleCompletePolygon}
                    disabled={polygonPoints.length < 3}
                    title="Close and complete the polygon (requires ≥3 vertices)"
                  >
                    ✓ Complete ({polygonPoints.length} pts)
                  </button>

                  <button
                    type="button"
                    className="tool-btn"
                    onClick={handleUndoVertex}
                    disabled={polygonPoints.length === 0}
                    title="Undo the last clicked vertex"
                  >
                    ↩ Undo Point
                  </button>
                </>
              )}

              <button
                type="button"
                className="tool-btn btn-cancel-draw"
                onClick={handleCancelDrawing}
                title="Cancel current drawing interaction"
              >
                ✕ Cancel
              </button>
            </>
          )}

          {aoiWkt && drawMode === 'none' && (
            <>
              <button
                type="button"
                className="tool-btn btn-fit-aoi"
                onClick={handleFitAoi}
                title="Zoom camera to fit the current AOI"
              >
                🔍 Focus AOI
              </button>

              <button
                type="button"
                className="tool-btn"
                onClick={handleExportGeoJson}
                title="Download this study area as a GeoJSON polygon"
              >
                💾 Export GeoJSON
              </button>

              <button
                type="button"
                className="tool-btn"
                onClick={handleCopyWkt}
                title="Copy WKT polygon string to clipboard"
              >
                {copiedWkt ? '✓ WKT Copied' : '📋 Copy WKT'}
              </button>

              <button
                type="button"
                className="tool-btn btn-clear-aoi"
                onClick={handleClearAoi}
                title="Clear current area selection"
              >
                ✕ Clear
              </button>
            </>
          )}
        </div>

        <div className="basemap-tools-group">
          <span className="toolbar-section-label">Basemap:</span>
          <button
            type="button"
            className={`basemap-pill-btn ${basemapStyle === 'dark' ? 'active' : ''}`}
            onClick={() => handleBasemapChange('dark')}
          >
            Dark OSM
          </button>
          <button
            type="button"
            className={`basemap-pill-btn ${basemapStyle === 'standard' ? 'active' : ''}`}
            onClick={() => handleBasemapChange('standard')}
          >
            Standard
          </button>
        </div>
      </div>

      {/* Main Canvas */}
      <div className="aoi-canvas-container">
        <div ref={mapContainerRef} className="aoi-leaflet-canvas" id="aoi-drawing-canvas" />

        {/* Live Drawing Guidance Banner */}
        {drawMode !== 'none' && (
          <div className="drawing-help-banner">
            {drawMode === 'rectangle' ? (
              <span>ℹ️ <strong>Drag to Draw:</strong> Click and drag on the map to define the bounding box</span>
            ) : (
              <span>
                ℹ️ <strong>Polygon Mode:</strong> Click along river margin. Click <strong>✓ Complete</strong> when done ({polygonPoints.length} vertices added)
              </span>
            )}
          </div>
        )}

        {/* Live Coordinates Badge */}
        <div className="aoi-coords-overlay">
          <span className="aoi-coords-dot" />
          {mouseCoords ? (
            <span className="aoi-coords-text">
              {mouseCoords.lat.toFixed(4)}° N, {mouseCoords.lon.toFixed(4)}° E
            </span>
          ) : (
            <span className="aoi-coords-text subtle">Hover map for coordinates</span>
          )}
        </div>

        {/* Geometry Validation Status Overlay */}
        {aoiWkt && (
          <div className={`aoi-validation-overlay ${validation.isValid ? 'valid' : 'invalid'}`}>
            <span className="validation-status-icon">{validation.isValid ? '✓' : '⚠️'}</span>
            <div className="validation-status-details">
              <span className="validation-status-title">
                {validation.isValid
                  ? `Valid Study Area: ${validation.areaKm2.toFixed(2)} km² (${(validation.areaKm2 * 100).toFixed(0)} ha)`
                  : 'Geometry Limitation'}
              </span>
              {validation.error && <span className="validation-status-err">{validation.error}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
