"""
Unit and Integration Tests for Earth Pulse Multi-Region, Extensible SAR Machine Learning
Validates configuration-driven architecture, dataset manifests, sensor adapters, multi-region
spatial partitioning, model versioning registry, parallel execution engine, and explainability buffers.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest

from src.core.config_loader import (
    load_region_config,
    load_sensor_config,
    load_model_config,
    load_feature_schema,
    validate_region_config,
    ConfigValidationError,
)
from src.core.dataset_manifest import DatasetManifest, DatasetRecord
from src.ml.adapters import (
    Sentinel1GRDAdapter,
    SensorAdapterRegistry,
    IncompatibleSensorError,
)
from src.ml.multi_region import (
    MultiRegionDatasetManager,
    ExperimentType,
)
from src.ml.registry import (
    ModelRegistry,
    ModelRegistryEntry,
)
from src.ml.engine import (
    ScientificInferenceEngine,
    MethodOutput,
)
from src.ml.prediction_record import (
    PredictionRecord,
    ExplainabilityBatchBuffer,
)
from scripts.intake_dataset import DatasetIntakePipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestConfigurationDrivenRegions:
    """Tests configuration loading, schema validation, and extensibility to future regions."""

    def test_load_jamuna_region_config(self):
        cfg = load_region_config("jamuna_sirajganj")
        assert cfg["region_id"] == "jamuna_sirajganj"
        assert "Jamuna" in cfg["region_name"]
        assert cfg["grid"]["crs"] == "EPSG:32645"
        assert cfg["grid"]["pixel_spacing_m"] == 20.0
        assert cfg["grid"]["raster_width"] == 1405
        assert cfg["grid"]["raster_height"] == 1393
        assert "june10" in cfg["acquisitions"]
        assert "july16" in cfg["acquisitions"]
        assert cfg["reference_labels"]["water_class_values"] == [6]

    def test_extensibility_to_future_region_patna(self):
        """Verifies that a future region (e.g. Patna, India) can be configured and validated without code changes."""
        future_cfg = {
            "region_id": "patna_ganges",
            "region_name": "Ganges River Reach (Patna, Bihar, India)",
            "aoi": {
                "wkt": "POLYGON((85.05 25.55, 85.30 25.55, 85.30 25.70, 85.05 25.70, 85.05 25.55))",
                "bbox": [85.05, 25.55, 85.30, 25.70]
            },
            "grid": {
                "crs": "EPSG:32645",
                "pixel_spacing_m": 20.0,
                "raster_width": 1200,
                "raster_height": 1100,
                "origin_x": 305000.0,
                "origin_y": 2830000.0,
            },
            "acquisitions": {
                "monsoon_2024": {
                    "acquisition_id": "s1a_patna_20240815",
                    "date": "2024-08-15",
                    "sensor_id": "sentinel1",
                }
            },
            "reference_labels": {
                "water_class_values": [6],
                "non_water_class_values": [5]
            }
        }
        # Validation should succeed without error
        validate_region_config(future_cfg)

        # Incomplete configuration should fail validation
        incomplete_cfg = future_cfg.copy()
        del incomplete_cfg["grid"]
        with pytest.raises(ConfigValidationError):
            validate_region_config(incomplete_cfg)

    def test_load_sensor_config_sentinel1(self):
        cfg = load_sensor_config("sentinel1")
        assert cfg["sensor_id"] == "sentinel1"
        assert cfg["radar_properties"]["band"] == "C-band"
        assert abs(cfg["radar_properties"]["center_frequency_ghz"] - 5.405) < 0.01
        assert "VV" in cfg["radar_properties"]["polarizations"]
        assert "VH" in cfg["radar_properties"]["polarizations"]
        assert cfg["compatibility"]["is_c_band"] is True
        assert cfg["compatibility"]["is_l_band"] is False

    def test_load_model_and_feature_configs(self):
        model_cfg = load_model_config("random_forest")
        assert model_cfg["model_type"] == "RandomForestClassifier"
        assert model_cfg["hyperparameters"]["n_estimators"] == 40
        assert model_cfg["decision_thresholds"]["optimal_probability_threshold"] == 0.35

        feat_cfg = load_feature_schema("sar_features")
        assert feat_cfg["feature_schema_version"] == "1.0.0"
        feat_names = [f["name"] for f in feat_cfg["features"]]
        assert feat_names == ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]


class TestSensorAdaptersAndCompatibility:
    """Tests sensor adapter feature extraction, bounds checking, and cross-frequency rejection."""

    def test_sentinel1_adapter_feature_extraction(self):
        adapter = Sentinel1GRDAdapter()
        assert adapter.sensor_id == "sentinel1"
        assert adapter.supported_band == "C-band"

        # Synthetic VV and VH backscatter rasters
        np.random.seed(42)
        vv = np.random.uniform(-25.0, -10.0, size=(50, 50)).astype(np.float32)
        vh = np.random.uniform(-32.0, -15.0, size=(50, 50)).astype(np.float32)

        features = adapter.extract_features(vv, vh)
        assert len(features) == 6
        assert "vv_db" in features
        assert "vh_db" in features
        assert "vv_minus_vh_db" in features
        assert "cross_pol_ratio" in features
        assert "texture_vv" in features
        assert "texture_vh" in features

        # Verify cross-pol ratio formula: 10 ** ((vv - vh) / 10)
        expected_diff = vv - vh
        assert np.allclose(features["vv_minus_vh_db"], expected_diff)
        expected_ratio = np.clip(10.0 ** (expected_diff / 10.0), 0.0, 100.0)
        assert np.allclose(features["cross_pol_ratio"], expected_ratio)

        # Validate physics bounds
        bounds_status = adapter.validate_physics_bounds(features)
        assert all(bounds_status.values())

    def test_incompatible_frequency_rejection(self):
        """Asserts that L-band or missing polarizations are strictly rejected by the C-band adapter."""
        adapter = Sentinel1GRDAdapter()

        # Test L-band metadata (e.g. NISAR or ALOS-2)
        l_band_meta = {
            "sensor": "nisar",
            "band": "L-band",
            "polarization": ["HH", "HV"]
        }
        compat, reason = adapter.check_compatibility(l_band_meta)
        assert compat is False
        assert "Incompatible sensor" in reason or "Incompatible frequency" in reason

        # Test missing VH crosspol
        single_pol_meta = {
            "sensor": "sentinel1",
            "band": "C-band",
            "polarization": ["VV"]
        }
        compat, reason = adapter.check_compatibility(single_pol_meta)
        assert compat is False
        assert "requires both VV and VH" in reason


class TestDatasetManifestAndProvenance:
    """Tests the reusable dataset manifest, record queries, and SHA-256 verification."""

    def test_dataset_manifest_loading_and_filtering(self):
        manifest = DatasetManifest()
        assert len(manifest.records) >= 8

        # Filter by region
        jamuna_records = manifest.filter(region_id="jamuna_sirajganj")
        assert len(jamuna_records) >= 8

        # Filter by sensor
        s1_records = manifest.filter(sensor="sentinel1")
        assert len(s1_records) >= 6

        # Filter by reference availability
        ref_records = manifest.filter(has_reference=True)
        assert len(ref_records) == len(jamuna_records)

    def test_dataset_manifest_checksum_verification(self):
        manifest = DatasetManifest()
        # Verify raw S1 zip checksums
        assert manifest.verify_file_checksum("s1a_iw_grd_20240610_raw") is True
        assert manifest.verify_file_checksum("s1a_iw_grd_20240716_raw") is True
        # Verify filtered Lee 5x5 rasters
        assert manifest.verify_file_checksum("s1a_iw_grd_20240610_filtered_lee5x5") is True
        assert manifest.verify_file_checksum("s1a_iw_grd_20240716_filtered_lee5x5") is True


class TestModelRegistryAndVersioning:
    """Tests model registration, duplicate protection, and explicit promotion criteria."""

    def test_registered_phase7a_model_retrieval(self):
        registry = ModelRegistry()
        model = registry.get_model("phase7a_rf_jamuna_v1")
        assert model is not None
        assert model.version == "1.0.0"
        assert model.region_coverage == ["jamuna_sirajganj"]
        assert model.sensor_compatibility == ["sentinel1"]
        assert model.status == "RETAINED_AS_PROBABILITY_LAYER"
        assert model.held_out_test_metrics["recall"] >= 0.90
        assert model.held_out_test_metrics["f1_score"] >= 0.60

    def test_prevent_overwriting_registered_model(self):
        registry = ModelRegistry()
        entry = registry.get_model("phase7a_rf_jamuna_v1")
        assert entry is not None
        # Attempting to re-register the same model ID must raise ValueError
        with pytest.raises(ValueError, match="already registered"):
            registry.register_model(entry, verify_artifact=False)

    def test_model_promotion_evaluation_gate(self):
        registry = ModelRegistry()
        # phase7a_rf_jamuna_v1 has specificity = 0.2523 (< 0.70) and precision = 0.4477 (< 0.55)
        # Attempting to promote under standard criteria must fail
        promoted, failures = registry.promote_model("phase7a_rf_jamuna_v1")
        assert promoted is False
        assert len(failures) > 0
        assert any("specificity" in f for f in failures)
        assert any("precision" in f for f in failures)


class TestMultiRegionSpatialPartitioning:
    """Tests spatially grouped block partitioning and zero-leakage cross-region transfer."""

    def test_multi_region_block_isolation(self):
        # Create synthetic dataset with two regions
        data = []
        for reg in ["jamuna_sirajganj", "patna_ganges"]:
            for b in range(10):
                for p in range(20):
                    data.append({
                        "region_id": reg,
                        "block_id": f"block_{b}",
                        "vv_db": -20.0,
                        "label": p % 2
                    })
        df = pd.DataFrame(data)

        # Regional / Multi-region partitioning
        tr_df, va_df, te_df = MultiRegionDatasetManager.partition_samples(
            df, experiment_type=ExperimentType.MULTI_REGION, random_seed=42
        )

        tr_blocks = set(tr_df["composite_block_id"])
        va_blocks = set(va_df["composite_block_id"])
        te_blocks = set(te_df["composite_block_id"])

        # Assert absolute zero spatial leakage
        assert len(tr_blocks.intersection(va_blocks)) == 0
        assert len(tr_blocks.intersection(te_blocks)) == 0
        assert len(va_blocks.intersection(te_blocks)) == 0

    def test_cross_region_holdout_protection(self):
        # Create synthetic dataset with two regions
        data = []
        for reg in ["region_a", "region_b"]:
            for b in range(10):
                for p in range(10):
                    data.append({
                        "region_id": reg,
                        "block_id": f"b_{b}",
                        "vv_db": -18.0,
                        "label": p % 2
                    })
        df = pd.DataFrame(data)

        tr_df, va_df, te_df = MultiRegionDatasetManager.partition_samples(
            df,
            experiment_type=ExperimentType.CROSS_REGION_TRANSFER,
            train_regions=["region_a"],
            test_regions=["region_b"],
            random_seed=42,
        )

        # Region A must be exclusively in train and val
        assert set(tr_df["region_id"].unique()) == {"region_a"}
        assert set(va_df["region_id"].unique()) == {"region_a"}
        # Region B must be exclusively in test
        assert set(te_df["region_id"].unique()) == {"region_b"}

    def test_regional_sample_balance_audit(self):
        df_imbalanced = pd.DataFrame({
            "region_id": ["region_large"] * 850 + ["region_small"] * 150
        })
        audit = MultiRegionDatasetManager.audit_regional_sample_distribution(df_imbalanced)
        assert audit["is_imbalanced"] is True
        assert audit["dominating_region"] == "region_large"
        assert "warning" in audit and audit["warning"] is not None


class TestParallelInferenceEngineAndExplainability:
    """Tests parallel execution of Otsu vs. RF and Phase 7B explainability buffer."""

    def test_parallel_engine_independent_execution(self):
        np.random.seed(42)
        shape = (40, 40)
        vv = np.random.uniform(-30.0, -10.0, size=shape).astype(np.float32)
        vh = np.random.uniform(-35.0, -15.0, size=shape).astype(np.float32)

        # 1. Deterministic baseline execution
        otsu_out = ScientificInferenceEngine.run_deterministic_otsu(
            vv, vh, vv_threshold=-16.0, vh_threshold=-23.5
        )
        assert otsu_out.is_primary_baseline is True
        assert otsu_out.method_name == "deterministic_otsu"
        assert otsu_out.probability_map is None
        assert otsu_out.water_mask.shape == shape

        # 2. Mock RF execution
        class MockRF:
            def predict_proba(self, X):
                # Return dummy probabilities
                n = len(X)
                p1 = np.clip(-X[:, 0] / 30.0, 0.0, 1.0)
                return np.column_stack([1.0 - p1, p1])

        features = {
            "vv_db": vv,
            "vh_db": vh,
            "vv_minus_vh_db": vv - vh,
            "cross_pol_ratio": np.ones(shape, dtype=np.float32),
            "texture_vv": np.ones(shape, dtype=np.float32),
            "texture_vh": np.ones(shape, dtype=np.float32),
        }

        rf_out = ScientificInferenceEngine.run_random_forest(
            features, MockRF(), probability_threshold=0.35
        )
        assert rf_out.is_primary_baseline is False
        assert rf_out.probability_map is not None
        assert rf_out.uncertainty_map is not None

        # 3. Model comparison without blending
        comp = ScientificInferenceEngine.compare_methods(otsu_out, rf_out)
        assert "agreement_percentage" in comp
        assert "water_detection_iou" in comp
        assert "contingency_table" in comp

    def test_explainability_batch_buffer_preparation(self):
        buffer = ExplainabilityBatchBuffer(
            model_version="phase7a_rf_jamuna_v1",
            region_id="jamuna_sirajganj",
            dataset_id="s1a_iw_grd_20240610_filtered_lee5x5",
            decision_threshold=0.35,
        )

        feat_names = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
        feat_vals = [-21.4, -28.2, 6.8, 4.78, 1.2, 0.9]

        rec = buffer.add_prediction(
            feature_names=feat_names,
            feature_values=feat_vals,
            prediction_probability=0.82,
            pixel_row=120,
            pixel_col=340,
            utm_x=762000.0,
            utm_y=2735000.0,
            ground_truth_scl=6,
        )

        assert rec.binary_prediction == 1
        assert rec.prediction_probability == 0.82

        df = buffer.to_dataframe()
        assert len(df) == 1
        assert df["model_version"].iloc[0] == "phase7a_rf_jamuna_v1"
        assert df["region_id"].iloc[0] == "jamuna_sirajganj"
        assert df["vv_db"].iloc[0] == -21.4
        assert df["ground_truth_scl"].iloc[0] == 6

    def test_intake_pipeline_on_aligned_raster(self):
        pipeline = DatasetIntakePipeline()
        aligned_tif = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
        assessment = pipeline.inspect_dataset(
            file_path=aligned_tif,
            region_hint="jamuna_sirajganj",
            sensor_hint="sentinel1",
        )
        assert assessment.file_exists is True
        assert assessment.sensor_identified == "sentinel1"
        assert assessment.crs_identified == "EPSG:32645"
        assert assessment.feature_compatibility["compatible"] is True
        assert assessment.use_case_determination == "REGIONAL_AND_MULTI_REGION_TRAINING"
        assert assessment.intake_status == "VALIDATED_FOR_TRAINING"

