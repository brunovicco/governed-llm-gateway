"""Contracts for the pinned credential-free local observability foundation."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_PATH = _ROOT / "compose.observability.yml"
_COLLECTOR_PATH = _ROOT / "deploy/observability/otel-collector.yaml"
_TEMPO_PATH = _ROOT / "deploy/observability/tempo.yaml"
_GRAFANA_DATASOURCE_PATH = _ROOT / "deploy/observability/grafana-datasources.yaml"

_EXPECTED_IMAGES = (
    "otel/opentelemetry-collector-contrib:0.160.0",
    "grafana/tempo:3.0.3",
    "grafana/grafana:13.2.1",
)
_BANNED_SECRET_TERMS = (
    "password:",
    "api_key:",
    "apikey:",
    "authorization:",
    "token:",
    "secret:",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_observability_images_are_exactly_pinned_and_network_is_internal() -> None:
    compose = _text(_COMPOSE_PATH)

    for image in _EXPECTED_IMAGES:
        assert compose.count(f"image: {image}") == 1
    assert "image: latest" not in compose
    assert ":latest" not in compose
    assert "  observability:\n    internal: true\n" in compose


def test_every_host_published_port_is_loopback_only() -> None:
    compose = _text(_COMPOSE_PATH)

    assert compose.count("127.0.0.1:4318:4318") == 1
    assert compose.count("127.0.0.1:3000:3000") == 1
    assert "0.0.0.0:4318:4318" not in compose
    assert "0.0.0.0:3000:3000" not in compose
    assert "3200:3200" not in compose


def test_containers_use_explicit_least_privilege_defaults() -> None:
    compose = _text(_COMPOSE_PATH)

    assert compose.count("read_only: true") == 3
    assert compose.count("      - ALL") == 3
    assert compose.count("      - no-new-privileges:true") == 3
    assert "tempo-data:/var/tempo" in compose
    assert "grafana-data:/var/lib/grafana" in compose


def test_collector_exports_only_metadata_traces_to_internal_tempo() -> None:
    collector = _text(_COLLECTOR_PATH)

    assert "endpoint: 0.0.0.0:4318" in collector
    assert collector.count("otlp/tempo") == 2
    assert "endpoint: tempo:4317" in collector
    assert "processors:\n  batch: {}" in collector
    assert "      receivers:\n        - otlp" in collector
    assert "      processors:\n        - batch" in collector
    assert "      exporters:\n        - otlp/tempo" in collector


def test_tempo_uses_internal_otlp_local_storage_and_tempo3_retention() -> None:
    tempo = _text(_TEMPO_PATH)

    assert "http_listen_port: 3200" in tempo
    assert "endpoint: 0.0.0.0:4317" in tempo
    assert "backend: local" in tempo
    assert "path: /var/tempo/traces" in tempo
    assert "path: /var/tempo/wal" in tempo
    assert "backend_worker:\n  compaction:\n    block_retention: 24h\n" in tempo
    assert "\ncompactor:" not in tempo
    assert "backend: s3" not in tempo
    assert "backend: gcs" not in tempo
    assert "backend: azure" not in tempo


def test_grafana_provisions_only_internal_tempo_datasource() -> None:
    datasource = _text(_GRAFANA_DATASOURCE_PATH)

    assert datasource.count("  - name: Tempo") == 1
    assert "    uid: tempo" in datasource
    assert "    type: tempo" in datasource
    assert "    access: proxy" in datasource
    assert "    url: http://tempo:3200" in datasource
    assert "    isDefault: true" in datasource
    assert "    editable: false" in datasource
    assert "localhost:3200" not in datasource
    assert "127.0.0.1:3200" not in datasource


def test_observability_configuration_contains_no_secrets_saas_or_langfuse() -> None:
    raw = "\n".join(
        _text(path).lower()
        for path in (
            _COMPOSE_PATH,
            _COLLECTOR_PATH,
            _TEMPO_PATH,
            _GRAFANA_DATASOURCE_PATH,
        )
    )

    for banned_term in _BANNED_SECRET_TERMS:
        assert banned_term not in raw
    assert "langfuse" not in raw
    assert "datadog" not in raw
    assert "otlphttp/" not in raw
