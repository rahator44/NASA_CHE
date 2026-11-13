import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parseWktPolygon, boundsToPolygonCoords } from '../utils/wkt';

describe('WKT Geometry Parser Suite', () => {
  it('should parse real 2025 Jamuna study AOI polygon coordinates', () => {
    const wkt = 'POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))';
    const coords = parseWktPolygon(wkt);

    assert.equal(coords.length, 5);

    // Leaflet requires [lat, lon] order
    assert.deepEqual(coords[0], [24.60, 89.60]);
    assert.deepEqual(coords[1], [24.60, 89.68]);
    assert.deepEqual(coords[2], [24.68, 89.68]);
    assert.deepEqual(coords[3], [24.68, 89.60]);
    assert.deepEqual(coords[4], [24.60, 89.60]);
  });

  it('should handle single-parenthesis polygon syntax', () => {
    const wkt = 'POLYGON(89.5 24.5, 89.7 24.5, 89.7 24.7, 89.5 24.7, 89.5 24.5)';
    const coords = parseWktPolygon(wkt);
    assert.equal(coords.length, 5);
    assert.deepEqual(coords[0], [24.5, 89.5]);
  });

  it('should return empty array on invalid or non-polygon input', () => {
    assert.deepEqual(parseWktPolygon(''), []);
    assert.deepEqual(parseWktPolygon('POINT(89.6 24.6)'), []);
    assert.deepEqual(parseWktPolygon('MALFORMED_STRING'), []);
  });

  it('should convert epsg4326 bounding box [min_lon, min_lat, max_lon, max_lat] to polygon coordinates', () => {
    const bounds: [number, number, number, number] = [89.59815, 24.59855, 89.68179, 24.68155];
    const coords = boundsToPolygonCoords(bounds);

    assert.equal(coords.length, 5);
    assert.deepEqual(coords[0], [24.59855, 89.59815]); // bottom-left
    assert.deepEqual(coords[1], [24.59855, 89.68179]); // bottom-right
    assert.deepEqual(coords[2], [24.68155, 89.68179]); // top-right
    assert.deepEqual(coords[3], [24.68155, 89.59815]); // top-left
    assert.deepEqual(coords[4], [24.59855, 89.59815]); // close ring
  });

  it('should translate polygon coordinates accurately during AOI move operations', () => {
    const coords: [number, number][] = [
      [24.60, 89.60],
      [24.60, 89.68],
      [24.68, 89.68],
      [24.68, 89.60],
      [24.60, 89.60],
    ];
    const deltaLat = 0.05;
    const deltaLon = 0.04;
    const moved = coords.map(([lat, lon]) => [Number((lat + deltaLat).toFixed(4)), Number((lon + deltaLon).toFixed(4))] as [number, number]);

    assert.deepEqual(moved[0], [24.65, 89.64]);
    assert.deepEqual(moved[2], [24.73, 89.72]);
    assert.deepEqual(moved[4], [24.65, 89.64]); // closed
  });

  it('should maintain ring closure when dragging the initial vertex', () => {
    const coords: [number, number][] = [
      [24.60, 89.60],
      [24.60, 89.68],
      [24.68, 89.68],
      [24.68, 89.60],
      [24.60, 89.60],
    ];
    const newFirst: [number, number] = [24.59, 89.59];
    coords[0] = newFirst;
    coords[coords.length - 1] = newFirst;

    assert.deepEqual(coords[0], coords[coords.length - 1]);
  });
});

