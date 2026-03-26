import threading
from typing import Dict
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from dakv.logging import get_logger


logger = get_logger()


manifest_queries_total = Counter(
    'dakv_manifest_queries_total',
    'Total manifest queries'
)

manifest_hit_total = Counter(
    'dakv_manifest_hit_total',
    'Total manifest hits'
)

remote_critical_bytes_total = Counter(
    'dakv_remote_critical_bytes_total',
    'Total critical bytes transferred'
)

remote_refine_bytes_total = Counter(
    'dakv_remote_refine_bytes_total',
    'Total refinement bytes transferred'
)

remote_critical_fail_total = Counter(
    'dakv_remote_critical_fail_total',
    'Total critical load failures'
)

refine_drop_total = Counter(
    'dakv_refine_drop_total',
    'Total refinement drops'
)

recompute_fallback_total = Counter(
    'dakv_recompute_fallback_total',
    'Total recompute fallbacks'
)

ttft_ms = Histogram(
    'dakv_ttft_ms',
    'Time to first token in milliseconds',
    buckets=[10, 50, 100, 200, 500, 1000, 2000, 5000]
)

tpot_ms = Histogram(
    'dakv_tpot_ms',
    'Time per output token in milliseconds',
    buckets=[5, 10, 20, 50, 100, 200]
)


class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.request_metrics: Dict[str, dict] = {}
    
    def record_manifest_query(self, hit: bool):
        manifest_queries_total.inc()
        if hit:
            manifest_hit_total.inc()
    
    def record_critical_bytes(self, nbytes: int):
        remote_critical_bytes_total.inc(nbytes)
    
    def record_refine_bytes(self, nbytes: int):
        remote_refine_bytes_total.inc(nbytes)
    
    def record_critical_fail(self):
        remote_critical_fail_total.inc()
    
    def record_refine_drop(self):
        refine_drop_total.inc()
    
    def record_recompute(self):
        recompute_fallback_total.inc()
    
    def record_ttft(self, ttft_value: float):
        ttft_ms.observe(ttft_value)
    
    def record_tpot(self, tpot_value: float):
        tpot_ms.observe(tpot_value)
    
    def record_request_metric(self, request_id: str, metric_dict: dict):
        with self.lock:
            self.request_metrics[request_id] = metric_dict


_global_collector: MetricsCollector = None


def get_metrics_collector() -> MetricsCollector:
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def start_metrics_server(port: int = 9090):
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server: {e}")
