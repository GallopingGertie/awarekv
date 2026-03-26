import threading
from dakv.common.types import NetworkEstimate
from dakv.common.time_utils import current_time_ms
from dakv.logging import get_logger


logger = get_logger()


class BandwidthEstimator:
    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.ewma_bps: float = 1_000_000_000.0
        self.ewma_rtt_ms: float = 10.0
        self.lock = threading.Lock()
        self.last_update_ms = 0
    
    def update(self, nbytes: int, duration_ms: float, rtt_ms: float = None):
        with self.lock:
            if duration_ms > 0:
                measured_bps = (nbytes * 8 * 1000.0) / duration_ms
                self.ewma_bps = self.alpha * measured_bps + (1 - self.alpha) * self.ewma_bps
            
            if rtt_ms is not None and rtt_ms > 0:
                self.ewma_rtt_ms = self.alpha * rtt_ms + (1 - self.alpha) * self.ewma_rtt_ms
            
            self.last_update_ms = current_time_ms()
            
            logger.debug(f"Bandwidth estimate updated: {self.ewma_bps/1e9:.2f} Gbps, RTT: {self.ewma_rtt_ms:.1f} ms")
    
    def get_estimate(self) -> NetworkEstimate:
        with self.lock:
            return NetworkEstimate(
                bandwidth_bps=self.ewma_bps,
                rtt_ms=self.ewma_rtt_ms,
                loss_rate=0.0,
                last_update_ms=self.last_update_ms
            )
