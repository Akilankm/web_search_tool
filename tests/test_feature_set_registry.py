import json

from src.product_evidence_harness.agent_service.orchestrator import FeatureSetRegistry


def test_registry_resolves_only_inside_private_root(tmp_path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    feature_file = private / "toy_features.json"
    feature_file.write_text(json.dumps({"features_to_code": ["feature_a"]}), encoding="utf-8")
    registry = FeatureSetRegistry(private)
    assert registry.resolve("toy_features") == feature_file.resolve()


def test_registry_rejects_traversal(tmp_path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    registry = FeatureSetRegistry(private)
    try:
        registry.resolve("../../secret")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Traversal-like input must not resolve")
