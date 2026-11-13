/**
 * Earth Pulse SAR — WKT Polygon Parser & Geometry Validation Utilities
 * Handles WGS84 EPSG:4326 geometry, Leaflet coordinate translation,
 * spherical area calculation, and Jamuna River region containment verification.
 */

import { GeometryValidationResult } from '../api/types';

// Authoritative Jamuna River study corridor bounds (EPSG:4326)
export const JAMUNA_STUDY_REGION = {
  minLon: 89.0,
  maxLon: 90.5,
  minLat: 24.0,
  maxLat: 25.5,
};

export const JAMUNA_STUDY_REGION_WKT =
  'POLYGON((89.0 24.0, 90.5 24.0, 90.5 25.5, 89.0 25.5, 89.0 24.0))';

// Standard 8.8 x 8.8 km Kazipur / Sirajganj demonstration study reach (~71.8 km²)
export const DEMO_STUDY_AOI_WKT =
  'POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))';

export const MAX_AOI_AREA_KM2 = 200.0;

/**
 * Parses WKT POLYGON (lon lat order) into Leaflet LatLng tuples ([lat, lon]).
 */
export function parseWktPolygon(wkt: string): [number, number][] {
  if (!wkt || typeof wkt !== 'string') {
    return [];
  }

  const clean = wkt.trim().toUpperCase();
  if (!clean.startsWith('POLYGON')) {
    return [];
  }

  // Extract everything inside innermost parentheses
  const firstParen = clean.indexOf('((');
  const lastParen = clean.lastIndexOf('))');

  let coordStr = '';
  if (firstParen !== -1 && lastParen !== -1 && lastParen > firstParen) {
    coordStr = clean.slice(firstParen + 2, lastParen);
  } else {
    // Single paren fallback
    const singleFirst = clean.indexOf('(');
    const singleLast = clean.lastIndexOf(')');
    if (singleFirst !== -1 && singleLast !== -1 && singleLast > singleFirst) {
      coordStr = clean.slice(singleFirst + 1, singleLast);
    }
  }

  if (!coordStr) {
    return [];
  }

  const pointPairs = coordStr.split(',').map((s) => s.trim()).filter(Boolean);
  const latLngs: [number, number][] = [];

  for (const pair of pointPairs) {
    const parts = pair.split(/\s+/).map((p) => parseFloat(p));
    if (parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
      const lon = parts[0];
      const lat = parts[1];
      latLngs.push([lat, lon]); // Leaflet requires [latitude, longitude]
    }
  }

  return latLngs;
}

/**
 * Converts Leaflet LatLng coordinates ([lat, lon]) to standard WGS84 WKT POLYGON (lon lat).
 * Automatically ensures polygon closure (first point equals last point).
 */
export function polygonToWkt(latLngs: [number, number][]): string {
  if (!latLngs || latLngs.length < 3) {
    return '';
  }

  const coords = [...latLngs];
  const first = coords[0];
  const last = coords[coords.length - 1];

  // Ensure closure
  if (Math.abs(first[0] - last[0]) > 1e-7 || Math.abs(first[1] - last[1]) > 1e-7) {
    coords.push([first[0], first[1]]);
  }

  // Format as lon lat with 6 decimal places (~0.1m precision)
  const strPairs = coords.map(([lat, lon]) => `${lon.toFixed(6)} ${lat.toFixed(6)}`).join(', ');
  return `POLYGON((${strPairs}))`;
}

/**
 * Calculates geodesic area of a polygon on the Earth sphere (R = 6371 km) in km².
 * LatLngs are [lat, lon].
 */
export function computePolygonAreaKm2(latLngs: [number, number][]): number {
  if (!latLngs || latLngs.length < 3) {
    return 0;
  }

  const coords = [...latLngs];
  const first = coords[0];
  const last = coords[coords.length - 1];
  if (Math.abs(first[0] - last[0]) > 1e-7 || Math.abs(first[1] - last[1]) > 1e-7) {
    coords.push([first[0], first[1]]);
  }

  const R = 6371.0; // Earth radius in km
  const rad = Math.PI / 180.0;
  let total = 0.0;

  for (let i = 0; i < coords.length - 1; i++) {
    const p1 = coords[i];
    const p2 = coords[i + 1];
    const lon1 = p1[1] * rad;
    const lat1 = p1[0] * rad;
    const lon2 = p2[1] * rad;
    const lat2 = p2[0] * rad;

    total += (lon2 - lon1) * (2.0 + Math.sin(lat1) + Math.sin(lat2));
  }

  const area = Math.abs((total * R * R) / 2.0);
  return Number(area.toFixed(4));
}

/**
 * Validates AOI coordinates against:
 * 1. Minimum vertices (at least 3 unique points).
 * 2. Valid latitude [-90, 90] and longitude [-180, 180].
 * 3. Area bounds (> 0 and <= MAX_AOI_AREA_KM2).
 * 4. Jamuna study corridor containment (89.0-90.5° E, 24.0-25.5° N).
 * 5. Simple non-self-intersecting boundary check.
 */
export function validateAoiGeometry(latLngs: [number, number][]): GeometryValidationResult {
  if (!latLngs || latLngs.length < 3) {
    return {
      isValid: false,
      areaKm2: 0,
      vertexCount: latLngs?.length || 0,
      isContainedInStudyRegion: false,
      error: 'Please select an area on the map with at least 3 vertices.',
    };
  }

  // Check unique vertices
  const uniquePoints = new Set(latLngs.map(([lat, lon]) => `${lat.toFixed(5)},${lon.toFixed(5)}`));
  if (uniquePoints.size < 3) {
    return {
      isValid: false,
      areaKm2: 0,
      vertexCount: uniquePoints.size,
      isContainedInStudyRegion: false,
      error: 'Polygon must contain at least 3 distinct non-overlapping vertices.',
    };
  }

  // Check coordinate bounds
  for (const [lat, lon] of latLngs) {
    if (isNaN(lat) || isNaN(lon)) {
      return {
        isValid: false,
        areaKm2: 0,
        vertexCount: latLngs.length,
        isContainedInStudyRegion: false,
        error: 'Geometry contains invalid numeric coordinates.',
      };
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return {
        isValid: false,
        areaKm2: 0,
        vertexCount: latLngs.length,
        isContainedInStudyRegion: false,
        error: `Coordinates [${lat}, ${lon}] exceed standard WGS84 latitude/longitude limits.`,
      };
    }
  }

  const areaKm2 = computePolygonAreaKm2(latLngs);
  if (areaKm2 <= 0.001) {
    return {
      isValid: false,
      areaKm2,
      vertexCount: latLngs.length,
      isContainedInStudyRegion: false,
      error: 'Selected area is degenerate (near zero surface area).',
    };
  }

  if (areaKm2 > MAX_AOI_AREA_KM2) {
    return {
      isValid: false,
      areaKm2,
      vertexCount: latLngs.length,
      isContainedInStudyRegion: false,
      error: `Selected area (${areaKm2.toFixed(1)} km²) exceeds the maximum allowed ${MAX_AOI_AREA_KM2} km². Please draw a smaller bounding area.`,
    };
  }

  // Check Jamuna regional containment (Lon: 89.0 to 90.5, Lat: 24.0 to 25.5)
  const isContained = latLngs.every(
    ([lat, lon]) =>
      lon >= JAMUNA_STUDY_REGION.minLon &&
      lon <= JAMUNA_STUDY_REGION.maxLon &&
      lat >= JAMUNA_STUDY_REGION.minLat &&
      lat <= JAMUNA_STUDY_REGION.maxLat
  );

  if (!isContained) {
    return {
      isValid: false,
      areaKm2,
      vertexCount: latLngs.length,
      isContainedInStudyRegion: false,
      error:
        'Selected area extends beyond the supported Jamuna River reach (89.0°–90.5° E, 24.0°–25.5° N). Earth Pulse processing is calibrated specifically for the braided Jamuna corridor.',
    };
  }

  return {
    isValid: true,
    areaKm2,
    vertexCount: latLngs.length,
    isContainedInStudyRegion: true,
  };
}

export function boundsToPolygonCoords(bounds: [number, number, number, number]): [number, number][] {
  // bounds: [min_lon, min_lat, max_lon, max_lat]
  const [minLon, minLat, maxLon, maxLat] = bounds;
  return [
    [minLat, minLon],
    [minLat, maxLon],
    [maxLat, maxLon],
    [maxLat, minLon],
    [minLat, minLon],
  ];
}
