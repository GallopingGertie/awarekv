import time


def current_time_ms() -> int:
    return int(time.time() * 1000)


def current_time_us() -> int:
    return int(time.time() * 1000000)


class Timer:
    def __init__(self):
        self.start_time = 0
        self.end_time = 0
    
    def __enter__(self):
        self.start_time = current_time_ms()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = current_time_ms()
    
    def elapsed_ms(self) -> float:
        if self.end_time == 0:
            return current_time_ms() - self.start_time
        return self.end_time - self.start_time
    
    def elapsed_s(self) -> float:
        return self.elapsed_ms() / 1000.0
