"""Contracts for the pinned credential-free local observability foundation."""

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_PATH = _ROOT / "compose.observability.yml"
_COLLECTOR_PATH = _ROOT / "deploy/observability/otel-collector.yaml"
_TEMPO_PATH = _ROOT / "deploy/observability/tempo.yaml"
_GRAFANA_DATASOURCE_PATH = _ROOT / "deploy/observability/grafana-datasources.yaml"

_EXPECTED_IMAGES = {
    "otel-collector": "otel/opentelemetry-collector-contrib:0.160.0",
    "tempo": "grafana/tempo:3.0.3",
    "grafana": "grafana/grafana:13.2.1",
}
_BANNED_SECRET_KEY_PARTS = (
    "password",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "secret",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _walk_mapping_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        keys = [str(key) for key in value]
        for nested in value.values():
            keys.extend(_walk_mapping_keys(nested))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for nested in value:
            keys.extend(_walk_mapping_keys(nested))
        return keys
    return []


def test_observability_images_are_exactly_pinned_and_network_is_internal() -> None:
    compose = _load_yaml(_COMPOSE_PATH)
    services = compose["services"]

    assert {name: services[name]["image"] for name in _EXPECTED_IMAGES} == _EXPECTED_IMAGES
    assert all("latest" not in image for image in _EXPECTED_IMAGES.values())
    assert compose["networks"]["observability"]["internal"] is True


def test_every_host_published_port_is_loopback_only() -> None:
    compose = _load_yaml(_COMPOSE_PATH)

    published_ports = [
        str(port)
        for service in compose["services"].values()
        for port in service.get("ports", [])
    ]

    assert published_ports == ["127.0.0.1:4318:4318", "127.0.0.1:3000:3000"]
    assert all(port.startswith("127.0.0.1:") for port in published_ports)
    assert "ports" not in compose["services"]["tempo"]


def test_containers_use_explicit_least_privilege_defaults() -> None:
    compose = _load_yaml(_COMPOSE_PATH)

    for service in compose["services"].values():
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]

    assert "tempo-data:/var/tempo" in compose["services"]["tempo"]["volumes"]
    assert "grafana-data:/var/lib/grafana" in compose["services"]["grafana"]["volumes"]


def test_collector_exports_only_metadata_traces_to_internal_tempo() -> None:
    collector = _load_yaml(_COLLECTOR_PATH)
    traces = collector["service"]["pipelines"]["traces"]

    assert (
        collector["receivers"]["otlp"]["protocols"]["http"]["endpoint"] == "0.0.0.0:4318"
    )
    assert set(collector["exporters"]) == {"otlp/tempo"}
    assert collector["exporters"]["otlp/tempo"]["endpoint"] == "tempo:4317"
    assert traces == {
        "receivers": ["otlp"],
        "processors": ["batch"],
        "exporters": ["otlp/tempo"],
    }


def test_tempo_uses_internal_otlp_and_local_storage_only() -> None:
    tempo = _load_yaml(_TEMPO_PATH)

    assert tempo["server"]["http_listen_port"] == 3200
    assert tempo["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == (
        "0.0.0.0:4317"
    )
    assert tempo["storage"]["trace"]["backend"] == "local"
    assert tempo["storage"]["trace"]["local"]["path"] == "/var/tempo/traces"
    assert tempo["storage"]["trace"]["wal"]["path"] == "/var/tempo/wal"


def test_grafana_provisions_only_internal_tempo_datasource() -> None:
    datasource = _load_yaml(_GRAFANA_DATASOURCE_PATH)["datasources"]

    assert datasource == [
        {
            "name": "Tempo",
            "uid": "tempo",
            "type": "tempo",
            "access": "proxy",
            "url": "http://tempo:3200",
            "isDefault": True,
            "editable": False,
        }
    ]


def test_observability_configuration_contains_no_secret_keys_or_langfuse() -> None:
    documents = [
        _load_yaml(_COMPOSE_PATH),
        _load_yaml(_COLLECTOR_PATH),
        _load_yaml(_TEMPO_PATH),
        _load_yaml(_GRAFANA_DATASOURCE_PATH),
    ]

    keys = [key.lower() for document in documents for key in _walk_mapping_keys(document)]
    assert not any(part in key for key in keys for part in _BANNED_SECRET_KEY_PARTS)

    raw = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            _COMPOSE_PATH,
            _COLLECTOR_PATH,
            _TEMPO_PATH,
            _GRAFANA_DATASOURCE_PATH,
        )
    )
    assert "langfuse" not in raw
    assert "authorization:" not in raw
