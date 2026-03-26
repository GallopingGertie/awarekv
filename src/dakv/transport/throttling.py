import time


class Throttler:
    def __init__(self, bandwidth_bps: float):
        self.bandwidth_bps = bandwidth_bps
        self.last_send_time = 0
    
    def throttle(self, nbytes: int):
        if self.bandwidth_bps <= 0:
            return
        
        required_time_s = nbytes / self.bandwidth_bps
        
        now = time.time()
        elapsed = now - self.last_send_time
        
        if elapsed < required_time_s:
            sleep_time = required_time_s - elapsed
            time.sleep(sleep_time)
        
        self.last_send_time = time.time()
