"""
NanoStream Observability
Prometheus metrics instrumentation for FastAPI backend.

Metrics exposed at /metrics:
    nanostream_jobs_total          - Total encoding jobs by status/codec
    nanostream_encode_duration_s   - Encoding duration histogram
    nanostream_queue_depth         - Current queue depth by status
    nanostream_bandwidth_served_gb - Total bandwidth served
    nanostream_psnr_db             - PSNR quality gauge by codec
    nanostream_active_viewers      - Simulated active viewer count
    nanostream_compression_ratio   - Compression ratio by codec

Usage:
    from observability import instrument_app, metrics
    instrument_app(app)          # add /metrics endpoint
    metrics.job_submitted('h265')
    metrics.job_completed('h265', duration_s=142.3, ratio=3.5, psnr=36.2)
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Try importing prometheus_client; fail gracefully ─────────────────────────
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry, REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed. Run: pip install prometheus-client")


class _FakeMetric:
    """No-op metric for when Prometheus is not installed."""
    def labels(self, **kwargs): return self
    def inc(self, v=1): pass
    def dec(self, v=1): pass
    def set(self, v): pass
    def observe(self, v): pass
    def time(self): return _FakeCtx()

class _FakeCtx:
    def __enter__(self): return self
    def __exit__(self, *a): pass


def _make(cls, *args, **kwargs):
    """Create metric or return no-op if Prometheus unavailable."""
    if PROMETHEUS_AVAILABLE:
        try:
            return cls(*args, **kwargs)
        except Exception:
            return _FakeMetric()
    return _FakeMetric()


# ── Metric definitions ────────────────────────────────────────────────────────
JOBS_TOTAL = _make(
    Counter if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_jobs_total',
    'Total encoding jobs',
    ['status', 'codec'],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

ENCODE_DURATION = _make(
    Histogram if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_encode_duration_seconds',
    'Encoding job duration',
    ['codec'],
    buckets=[30, 60, 120, 300, 600, 1200, 3600],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

QUEUE_DEPTH = _make(
    Gauge if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_queue_depth',
    'Current queue depth',
    ['status'],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

BANDWIDTH_SERVED = _make(
    Counter if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_bandwidth_served_gb_total',
    'Total bandwidth served in GB',
    ['codec'],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

PSNR_GAUGE = _make(
    Gauge if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_psnr_db',
    'PSNR quality gauge',
    ['codec'],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

COMPRESSION_RATIO = _make(
    Gauge if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_compression_ratio',
    'Compression ratio achieved',
    ['codec'],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

ACTIVE_VIEWERS = _make(
    Gauge if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_active_viewers',
    'Simulated active viewer count',
) if PROMETHEUS_AVAILABLE else _FakeMetric()

ANALYSIS_DURATION = _make(
    Histogram if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_analysis_duration_seconds',
    'Content analysis duration',
    buckets=[1, 5, 10, 30, 60],
) if PROMETHEUS_AVAILABLE else _FakeMetric()

REQUEST_LATENCY = _make(
    Histogram if PROMETHEUS_AVAILABLE else _FakeMetric,
    'nanostream_http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint', 'status'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
) if PROMETHEUS_AVAILABLE else _FakeMetric()


# ── High-level metrics helper ─────────────────────────────────────────────────
class NanoStreamMetrics:
    """Clean interface to all NanoStream metrics."""

    def job_submitted(self, codec: str):
        """Record job submission."""
        JOBS_TOTAL.labels(status='submitted', codec=codec).inc()
        QUEUE_DEPTH.labels(status='queued').inc()

    def job_started(self, codec: str):
        """Record job starting."""
        QUEUE_DEPTH.labels(status='queued').dec()
        QUEUE_DEPTH.labels(status='processing').inc()

    def job_completed(
        self,
        codec: str,
        duration_s: float,
        compression_ratio: float = 0,
        psnr_db: float = 0,
        bandwidth_gb: float = 0,
    ):
        """Record job completion with quality metrics."""
        JOBS_TOTAL.labels(status='completed', codec=codec).inc()
        QUEUE_DEPTH.labels(status='processing').dec()
        ENCODE_DURATION.labels(codec=codec).observe(duration_s)

        if compression_ratio > 0:
            COMPRESSION_RATIO.labels(codec=codec).set(compression_ratio)
        if psnr_db > 0:
            PSNR_GAUGE.labels(codec=codec).set(psnr_db)
        if bandwidth_gb > 0:
            BANDWIDTH_SERVED.labels(codec=codec).inc(bandwidth_gb)

    def job_failed(self, codec: str):
        """Record job failure."""
        JOBS_TOTAL.labels(status='failed', codec=codec).inc()
        QUEUE_DEPTH.labels(status='processing').dec()

    def set_active_viewers(self, count: int):
        """Update active viewer count."""
        ACTIVE_VIEWERS.set(count)

    def record_analysis(self, duration_s: float):
        """Record content analysis duration."""
        ANALYSIS_DURATION.observe(duration_s)

    def record_request(self, method: str, endpoint: str, status: int, duration_s: float):
        """Record HTTP request."""
        REQUEST_LATENCY.labels(
            method=method, endpoint=endpoint, status=str(status)
        ).observe(duration_s)

    def update_queue(self, stats: dict):
        """Sync queue depth gauges from JobQueue stats."""
        for status in ['queued', 'processing', 'completed', 'failed']:
            QUEUE_DEPTH.labels(status=status).set(stats.get(status, 0))


# Singleton
metrics = NanoStreamMetrics()


# ── FastAPI middleware ────────────────────────────────────────────────────────
def instrument_app(app):
    """
    Add Prometheus /metrics endpoint and request timing middleware to FastAPI app.

    Usage:
        from observability import instrument_app
        instrument_app(app)
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus not available — /metrics endpoint disabled")
        return

    from fastapi import Request
    from fastapi.responses import Response

    @app.middleware('http')
    async def prometheus_middleware(request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        duration = time.time() - t0

        # Only track API endpoints, not static files
        path = request.url.path
        if not path.startswith('/static'):
            metrics.record_request(
                method=request.method,
                endpoint=path,
                status=response.status_code,
                duration_s=duration,
            )
        return response

    @app.get('/metrics', include_in_schema=False)
    async def prometheus_metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics")


# ── Context manager for timing ────────────────────────────────────────────────
class timer:
    """Context manager that records duration to a metric."""
    def __init__(self, record_fn):
        self.record_fn = record_fn
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *args):
        self.record_fn(time.time() - self.t0)


if __name__ == '__main__':
    print(f"Prometheus available: {PROMETHEUS_AVAILABLE}")

    # Demo metrics
    m = NanoStreamMetrics()
    m.job_submitted('h265')
    m.job_started('h265')
    m.job_completed('h265', duration_s=142.3, compression_ratio=3.55, psnr_db=36.2)
    m.set_active_viewers(1234)

    if PROMETHEUS_AVAILABLE:
        print("\nSample /metrics output:")
        print(generate_latest().decode()[:800])
    else:
        print("Install with: pip install prometheus-client")
