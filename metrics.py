"""Jour 5 : métriques métier Prometheus (no-op si prometheus_client n'est pas installé, ex. dans l'.exe)."""
try:
    from prometheus_client import Counter, Histogram

    OPENMETEO_LATENCY = Histogram(
        "openmeteo_request_duration_seconds",
        "Durée des appels à l'API Open-Meteo",
        ["endpoint"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )
    OPENMETEO_ERRORS = Counter(
        "openmeteo_request_errors", "Appels Open-Meteo en échec", ["endpoint"]
    )
    RELEVES_INSERTED = Counter("meteo_releves_inserted", "Relevés insérés dans SQLite")

    for _endpoint in ("forecast", "geocoding"):   # séries visibles dès 0 dans Grafana
        OPENMETEO_ERRORS.labels(_endpoint)
        OPENMETEO_LATENCY.labels(_endpoint)
except ImportError:                                # pragma: no cover
    class _Noop:
        def labels(self, *a, **k):
            return self

        def observe(self, *a, **k):
            pass

        def inc(self, *a, **k):
            pass

    OPENMETEO_LATENCY = OPENMETEO_ERRORS = RELEVES_INSERTED = _Noop()
