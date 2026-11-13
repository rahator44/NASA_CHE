import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  polygonToWkt,
  computePolygonAreaKm2,
  validateAoiGeometry,
  parseWktPolygon,
  DEMO_STUDY_AOI_WKT,
  JAMUNA_STUDY_REGION_WKT,
} from '../utils/wkt';
import { CatalogSearchResponse, CompatiblePair } from '../api/types';

describe('New Analysis & AOI Validation Suite', () => {
  it('should correctly format polygon coordinates into standard WKT string', () => {
    const latLngs: [number, number][] = [
      [24.60, 89.60],
      [24.60, 89.68],
      [24.68, 89.68],
      [24.68, 89.60],
    ];

    const wkt = polygonToWkt(latLngs);
    assert.match(wkt, /^POLYGON\(\(89\.600000 24\.600000/);
    // Standard WKT requires the first coordinate to close the polygon loop
    assert.ok(wkt.endsWith('89.600000 24.600000))'));
  });

  it('should compute spherical geodesic area accurately for Jamuna demonstration reach', () => {
    const points = parseWktPolygon(DEMO_STUDY_AOI_WKT);
    assert.ok(points.length >= 4);

    const areaKm2 = computePolygonAreaKm2(points);
    // The ~8.8 km x ~8.8 km Kazipur bounding box is approximately 76-78 km²
    assert.ok(areaKm2 > 70 && areaKm2 < 85, `Expected ~77 km², got ${areaKm2}`);
  });

  it('should validate Jamuna study area and verify containment', () => {
    const points = parseWktPolygon(DEMO_STUDY_AOI_WKT);
    const result = validateAoiGeometry(points);

    assert.equal(result.isValid, true);
    assert.equal(result.isContainedInStudyRegion, true);
    assert.equal(result.error, undefined);
    assert.ok(result.areaKm2 > 0 && result.areaKm2 <= 200.0);
  });

  it('should reject polygons with fewer than 3 vertices', () => {
    const twoPoints: [number, number][] = [
      [24.60, 89.60],
      [24.68, 89.68],
    ];
    const result = validateAoiGeometry(twoPoints);

    assert.equal(result.isValid, false);
    assert.match(result.error || '', /at least 3 vertices/);
  });

  it('should reject AOIs exceeding the 200 km² maximum compute budget', () => {
    // 0.5 deg x 0.5 deg box in Bangladesh is ~55 km x ~55 km ≈ ~3000 km²
    const largeBox: [number, number][] = [
      [24.20, 89.20],
      [24.20, 89.80],
      [24.80, 89.80],
      [24.80, 89.20],
    ];
    const result = validateAoiGeometry(largeBox);

    assert.equal(result.isValid, false);
    assert.match(result.error || '', /exceeds the maximum allowed 200 km²/);
  });

  it('should flag polygons outside the supported Jamuna corridor', () => {
    // Padma / Meghna / Bay of Bengal region: 22.0° N, 91.5° E
    const distantAoi: [number, number][] = [
      [22.00, 91.50],
      [22.00, 91.55],
      [22.05, 91.55],
      [22.05, 91.50],
    ];
    const result = validateAoiGeometry(distantAoi);

    assert.equal(result.isValid, false);
    assert.equal(result.isContainedInStudyRegion, false);
    assert.match(result.error || '', /extends beyond the supported Jamuna River reach/);
  });

  it('should parse satellite catalogue response and extract compatible observation pairs', () => {
    const mockCatalogPayload: CatalogSearchResponse = {
      total_scenes: 3,
      scenes: [
        {
          scene_name: 'S1A_IW_GRDH_1SDV_20240610T120000',
          acquisition_time: '2024-06-10T12:00:00Z',
          orbit_direction: 'DESCENDING',
          relative_orbit: 150,
          flight_direction: 'DESCENDING',
          polarization: 'VV+VH',
          download_url: 'https://asf.alaska.edu/s1a_20240610',
          size_mb: 850.5,
        },
        {
          scene_name: 'S1A_IW_GRDH_1SDV_20240622T120000',
          acquisition_time: '2024-06-22T12:00:00Z',
          orbit_direction: 'DESCENDING',
          relative_orbit: 150,
          flight_direction: 'DESCENDING',
          polarization: 'VV+VH',
          download_url: 'https://asf.alaska.edu/s1a_20240622',
          size_mb: 852.1,
        },
      ],
      compatible_pairs_count: 1,
      compatible_pairs: [
        {
          baseline: {
            scene_name: 'S1A_IW_GRDH_1SDV_20240610T120000',
            acquisition_time: '2024-06-10T12:00:00Z',
            orbit_direction: 'DESCENDING',
            relative_orbit: 150,
            flight_direction: 'DESCENDING',
            polarization: 'VV+VH',
            download_url: 'https://asf.alaska.edu/s1a_20240610',
            size_mb: 850.5,
          },
          change: {
            scene_name: 'S1A_IW_GRDH_1SDV_20240622T120000',
            acquisition_time: '2024-06-22T12:00:00Z',
            orbit_direction: 'DESCENDING',
            relative_orbit: 150,
            flight_direction: 'DESCENDING',
            polarization: 'VV+VH',
            download_url: 'https://asf.alaska.edu/s1a_20240622',
            size_mb: 852.1,
          },
          temporal_baseline_days: 12,
          metrics: {
            track_match: true,
            flight_direction_match: true,
            polarization_match: true,
          },
        },
      ],
      query_metadata: {
        aoi_wkt: DEMO_STUDY_AOI_WKT,
        start_date: '2024-06-01',
        end_date: '2024-06-30',
        cached: true,
      },
    };

    assert.equal(mockCatalogPayload.total_scenes, 3);
    assert.equal(mockCatalogPayload.compatible_pairs_count, 1);

    const pair: CompatiblePair = mockCatalogPayload.compatible_pairs[0];
    assert.equal(pair.temporal_baseline_days, 12);
    assert.equal(pair.metrics.track_match, true);
    assert.equal(pair.metrics.flight_direction_match, true);
    assert.equal(pair.metrics.polarization_match, true);
    assert.equal(pair.baseline.relative_orbit, pair.change.relative_orbit);
  });
});
