from typing import Dict, List
from dakv.common.time_utils import current_time_ms


class Event:
    def __init__(self, event_type: str, request_id: str, data: Dict = None):
        self.event_type = event_type
        self.request_id = request_id
        self.timestamp_ms = current_time_ms()
        self.data = data or {}


class EventTracer:
    def __init__(self):
        self.events: List[Event] = []
    
    def trace(self, event_type: str, request_id: str, data: Dict = None):
        event = Event(event_type, request_id, data)
        self.events.append(event)
    
    def get_events(self, request_id: str = None) -> List[Event]:
        if request_id is None:
            return self.events
        return [e for e in self.events if e.request_id == request_id]
    
    def clear(self):
        self.events.clear()
