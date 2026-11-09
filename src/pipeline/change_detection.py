"""
Multi-Temporal Flood Change Detection Engine for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Features:
- Rigorous 6-class multi-temporal transition mapping:
  Class 1: Persistent Water
  Class 2: Newly Inundated Candidate
  Class 3: Receded Water
  Class 4: Persistent Non-Water
  Class 5: Indeterminate Transition Floor (SNAP clipping floor)
  Class 6: NoData / Invalid Extent
- Strict Mathematical Reconciliation Invariant:
  Net Change = Gross Inundation - Gross Recession == Water(t2) - Water(t1)
- Connected components spatial clustering for newly inundated candidate areas
- GeoTIFF and GeoJSON vector output generation
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
from osgeo import gdal, ogr, osr
from scipy.ndimage import label, find_objects

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.ChangeDetection")

# Transition Classes
TRANS_PERSISTENT_WATER = 1
TRANS_NEWLY_INUNDATED = 2
TRANS_RECEDED_WATER = 3
TRANS_PERSISTENT_NON_WATER = 4
TRANS_INDETERMINATE = 5
TRANS_NODATA_INVALID = 6

PIXEL_SPACING_M = 20.0
PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004

# Water Mask Input Categories
MASK_NON_WATER = 0
MASK_CANDIDATE_WATER = 1
MASK_INDETERMINATE = 2
MASK_NODATA_INVALID = 3


class DynamicChangeDetector:
    """
    Coordinates multi-temporal flood transition mapping and area reconciliation.
    """

    @classmethod
    def detect_changes(
        cls,
        baseline_mask_tif: Path,
        change_mask_tif: Path,
        output_transition_tif: Path,
        output_metadata_json: Optional[Path] = None,
        output_vector_geojson: Optional[Path] = None,
        min_cluster_pixels: int = 5,
    ) -> Dict[str, Any]:
        """
        Compare two candidate water mask GeoTIFFs and produce reconciled transition outputs.
        """
        baseline_mask_tif = Path(baseline_mask_tif).resolve()
        change_mask_tif = Path(change_mask_tif).resolve()
        output_transition_tif = Path(output_transition_tif).resolve()
        output_transition_tif.parent.mkdir(parents=True, exist_ok=True)

        ds1 = gdal.Open(str(baseline_mask_tif), gdal.GA_ReadOnly)
        ds2 = gdal.Open(str(change_mask_tif), gdal.GA_ReadOnly)

        if ds1 is None or ds2 is None:
            raise FileNotFoundError("Could not open input mask GeoTIFFs")

        w1, h1 = ds1.RasterXSize, ds1.RasterYSize
        w2, h2 = ds2.RasterXSize, ds2.RasterYSize
        if (w1, h1) != (w2, h2):
            raise ValueError(f"Spatial dimension mismatch between masks: ({w1}, {h1}) vs ({w2}, {h2})")

        gt = ds1.GetGeoTransform()
        proj = ds1.GetProjection()

        m1 = ds1.GetRasterBand(1).ReadAsArray()
        m2 = ds2.GetRasterBand(1).ReadAsArray()
        ds1 = None
        ds2 = None

        # 1. Multi-temporal transition classification
        # Default to Class 6 (NoData / Invalid)
        trans = np.full((h1, w1), TRANS_NODATA_INVALID, dtype=np.uint8)

        # Priority 1: NoData
        is_nodata = (m1 == MASK_NODATA_INVALID) | (m2 == MASK_NODATA_INVALID)

        # Priority 2: Indeterminate
        is_indet = (~is_nodata) & ((m1 == MASK_INDETERMINATE) | (m2 == MASK_INDETERMINATE))

        # Priority 3: Definitive transitions
        is_definitive = (~is_nodata) & (~is_indet)
        is_persist_water = is_definitive & (m1 == MASK_CANDIDATE_WATER) & (m2 == MASK_CANDIDATE_WATER)
        is_newly_inundated = is_definitive & (m1 == MASK_NON_WATER) & (m2 == MASK_CANDIDATE_WATER)
        is_receded_water = is_definitive & (m1 == MASK_CANDIDATE_WATER) & (m2 == MASK_NON_WATER)
        is_persist_nonwater = is_definitive & (m1 == MASK_NON_WATER) & (m2 == MASK_NON_WATER)

        trans[is_persist_water] = TRANS_PERSISTENT_WATER
        trans[is_newly_inundated] = TRANS_NEWLY_INUNDATED
        trans[is_receded_water] = TRANS_RECEDED_WATER
        trans[is_persist_nonwater] = TRANS_PERSISTENT_NON_WATER
        trans[is_indet] = TRANS_INDETERMINATE
        trans[is_nodata] = TRANS_NODATA_INVALID

        # 2. Pixel counts and spatial area metrics
        n_persist_water = int(np.sum(trans == TRANS_PERSISTENT_WATER))
        n_newly_inundated = int(np.sum(trans == TRANS_NEWLY_INUNDATED))
        n_receded_water = int(np.sum(trans == TRANS_RECEDED_WATER))
        n_persist_nonwater = int(np.sum(trans == TRANS_PERSISTENT_NON_WATER))
        n_indeterminate = int(np.sum(trans == TRANS_INDETERMINATE))
        n_nodata = int(np.sum(trans == TRANS_NODATA_INVALID))

        n_valid_comparison = n_persist_water + n_newly_inundated + n_receded_water + n_persist_nonwater
        n_total_pixels = int(w1 * h1)

        # Area conversions
        area_persist_water_km2 = float(n_persist_water * PIXEL_AREA_KM2)
        area_newly_inundated_km2 = float(n_newly_inundated * PIXEL_AREA_KM2)
        area_receded_water_km2 = float(n_receded_water * PIXEL_AREA_KM2)
        area_persist_nonwater_km2 = float(n_persist_nonwater * PIXEL_AREA_KM2)
        area_indeterminate_km2 = float(n_indeterminate * PIXEL_AREA_KM2)
        area_valid_comparison_km2 = float(n_valid_comparison * PIXEL_AREA_KM2)
        area_total_aoi_km2 = float(n_total_pixels * PIXEL_AREA_KM2)

        # Reconciled Net Change
        net_change_pixels = n_newly_inundated - n_receded_water
        net_change_km2 = float(net_change_pixels * PIXEL_AREA_KM2)
        gross_inundation_km2 = area_newly_inundated_km2
        gross_recession_km2 = area_receded_water_km2

        # Verification of identity
        # In valid comparison domain: Water(t1) = persist + receded; Water(t2) = persist + newly_inun
        water_t1_pixels = n_persist_water + n_receded_water
        water_t2_pixels = n_persist_water + n_newly_inundated
        diff_water_pixels = water_t2_pixels - water_t1_pixels

        reconciliation_passed = (net_change_pixels == diff_water_pixels)
        if not reconciliation_passed:
            logger.error(
                "Scientific accounting identity failed: net_change=%d, diff_water=%d",
                net_change_pixels,
                diff_water_pixels,
            )

        # 3. Write Transition GeoTIFF
        driver = gdal.GetDriverByName("GTiff")
        out_ds = driver.Create(
            str(output_transition_tif),
            w1,
            h1,
            1,
            gdal.GDT_Byte,
            ["COMPRESS=LZW", "TILED=YES"],
        )
        out_ds.SetGeoTransform(gt)
        out_ds.SetProjection(proj)
        band = out_ds.GetRasterBand(1)
        band.WriteArray(trans)
        band.SetDescription("Flood_Transition_Classes_1to6")
        band.SetNoDataValue(TRANS_NODATA_INVALID)
        out_ds.FlushCache()
        out_ds = None

        # 4. Connected Components for Newly Inundated Clusters
        labeled_inun, num_features = label(trans == TRANS_NEWLY_INUNDATED)
        slices = find_objects(labeled_inun)

        clusters = []
        for i, sl in enumerate(slices, start=1):
            cluster_mask = (labeled_inun[sl] == i)
            px_count = int(np.sum(cluster_mask))
            if px_count >= min_cluster_pixels:
                y_indices, x_indices = np.where(cluster_mask)
                centroid_r = float(sl[0].start + np.mean(y_indices))
                centroid_c = float(sl[1].start + np.mean(x_indices))
                # Geo coordinates
                geo_x = gt[0] + centroid_c * gt[1] + centroid_r * gt[2]
                geo_y = gt[3] + centroid_c * gt[4] + centroid_r * gt[5]
                clusters.append({
                    "cluster_id": i,
                    "pixel_count": px_count,
                    "area_ha": float(px_count * PIXEL_AREA_HA),
                    "area_km2": float(px_count * PIXEL_AREA_KM2),
                    "centroid_utm": [geo_x, geo_y],
                })

        clusters.sort(key=lambda c: c["pixel_count"], reverse=True)

        # 5. Optional Vector GeoJSON Export of Inundation
        if output_vector_geojson and num_features > 0:
            cls._export_inundation_geojson(labeled_inun, gt, proj, output_vector_geojson, min_cluster_pixels)

        metadata = {
            "baseline_mask": str(baseline_mask_tif),
            "change_mask": str(change_mask_tif),
            "output_transition_raster": str(output_transition_tif),
            "dimensions": [w1, h1],
            "pixel_counts": {
                "persistent_water": n_persist_water,
                "newly_inundated": n_newly_inundated,
                "receded_water": n_receded_water,
                "persistent_non_water": n_persist_nonwater,
                "indeterminate_floor": n_indeterminate,
                "nodata_invalid": n_nodata,
                "valid_comparison": n_valid_comparison,
                "total_pixels": n_total_pixels,
            },
            "area_metrics_km2": {
                "persistent_water": area_persist_water_km2,
                "newly_inundated": area_newly_inundated_km2,
                "receded_water": area_receded_water_km2,
                "persistent_non_water": area_persist_nonwater_km2,
                "indeterminate_floor": area_indeterminate_km2,
                "valid_comparison_area": area_valid_comparison_km2,
                "total_study_aoi": area_total_aoi_km2,
                "net_candidate_water_change": net_change_km2,
                "gross_inundation": gross_inundation_km2,
                "gross_recession": gross_recession_km2,
            },
            "area_metrics_ha": {
                "persistent_water": float(n_persist_water * PIXEL_AREA_HA),
                "newly_inundated": float(n_newly_inundated * PIXEL_AREA_HA),
                "receded_water": float(n_receded_water * PIXEL_AREA_HA),
                "persistent_non_water": float(n_persist_nonwater * PIXEL_AREA_HA),
                "net_candidate_water_change": float(net_change_pixels * PIXEL_AREA_HA),
            },
            "reconciliation": {
                "net_equals_inundation_minus_recession": reconciliation_passed,
                "water_t1_pixels": water_t1_pixels,
                "water_t2_pixels": water_t2_pixels,
                "net_change_pixels": net_change_pixels,
            },
            "inundation_clusters": {
                "total_clusters_detected": num_features,
                "clusters_meeting_minimum_size": len(clusters),
                "top_10_largest_clusters": clusters[:10],
            },
        }

        if output_metadata_json:
            output_metadata_json = Path(output_metadata_json).resolve()
            output_metadata_json.parent.mkdir(parents=True, exist_ok=True)
            output_metadata_json.write_text(json.dumps(metadata, indent=2))

        return metadata

    @classmethod
    def _export_inundation_geojson(
        cls,
        labeled_inun: np.ndarray,
        gt: Tuple[float, ...],
        proj_wkt: str,
        output_geojson: Path,
        min_pixels: int = 5,
    ) -> None:
        """Vectorize newly inundated clusters to GeoJSON."""
        output_geojson = Path(output_geojson).resolve()
        output_geojson.parent.mkdir(parents=True, exist_ok=True)

        h, w = labeled_inun.shape
        mem_driver = gdal.GetDriverByName("MEM")
        mem_ds = mem_driver.Create("", w, h, 1, gdal.GDT_Int32)
        mem_ds.SetGeoTransform(gt)
        mem_ds.SetProjection(proj_wkt)
        band = mem_ds.GetRasterBand(1)
        band.WriteArray(labeled_inun.astype(np.int32))

        # Spatial reference
        srs = osr.SpatialReference()
        srs.ImportFromWkt(proj_wkt)

        # Output GeoJSON layer (in WGS84 EPSG:4326 for web map compatibility)
        srs_4326 = osr.SpatialReference()
        srs_4326.ImportFromEPSG(4326)
        coord_transform = osr.CoordinateTransformation(srs, srs_4326)

        json_driver = ogr.GetDriverByName("GeoJSON")
        if output_geojson.exists():
            output_geojson.unlink()

        json_ds = json_driver.CreateDataSource(str(output_geojson))
        layer = json_ds.CreateLayer("newly_inundated_clusters", srs_4326, ogr.wkbPolygon)

        id_field = ogr.FieldDefn("cluster_id", ogr.OFTInteger)
        layer.CreateField(id_field)
        px_field = ogr.FieldDefn("pixel_count", ogr.OFTInteger)
        layer.CreateField(px_field)
        ha_field = ogr.FieldDefn("area_ha", ogr.OFTReal)
        layer.CreateField(ha_field)

        # Polygonize
        poly_layer_ds = ogr.GetDriverByName("Memory").CreateDataSource("mem_poly")
        poly_layer = poly_layer_ds.CreateLayer("poly", srs, ogr.wkbPolygon)
        val_field = ogr.FieldDefn("val", ogr.OFTInteger)
        poly_layer.CreateField(val_field)

        gdal.Polygonize(band, None, poly_layer, 0, [], callback=None)

        # Filter by min_pixels and transform to EPSG:4326
        layer.StartTransaction()
        for feature in poly_layer:
            cluster_id = feature.GetField("val")
            if cluster_id <= 0:
                continue
            geom = feature.GetGeometryRef()
            if geom is None:
                continue
            # Calculate pixel count from area or clone
            area_m2 = geom.GetArea()
            px_count = int(round(area_m2 / (PIXEL_SPACING_M * PIXEL_SPACING_M)))
            if px_count >= min_pixels:
                geom_4326 = geom.Clone()
                geom_4326.Transform(coord_transform)
                new_feature = ogr.Feature(layer.GetLayerDefn())
                new_feature.SetGeometry(geom_4326)
                new_feature.SetField("cluster_id", cluster_id)
                new_feature.SetField("pixel_count", px_count)
                new_feature.SetField("area_ha", float(px_count * PIXEL_AREA_HA))
                layer.CreateFeature(new_feature)
                new_feature = None

        layer.CommitTransaction()
        json_ds = None
        mem_ds = None

