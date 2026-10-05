"""Small in-memory latency counters; route templates only, never request content."""
import threading


class RequestMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.routes = {}

    def record(self, route, duration_ms, status):
        if not route or not route.startswith('/api/'):
            return
        with self.lock:
            if route not in self.routes and len(self.routes) >= 64:
                return
            item = self.routes.setdefault(route, {'requests': 0, 'errors': 0, 'total_ms': 0, 'max_ms': 0})
            item['requests'] += 1
            item['errors'] += status >= 400
            item['total_ms'] += duration_ms
            item['max_ms'] = max(item['max_ms'], duration_ms)

    def snapshot(self):
        with self.lock:
            return {route: {'requests': value['requests'], 'errors': value['errors'],
                           'mean_ms': round(value['total_ms'] / value['requests'], 2),
                           'max_ms': round(value['max_ms'], 2)} for route, value in self.routes.items()}
