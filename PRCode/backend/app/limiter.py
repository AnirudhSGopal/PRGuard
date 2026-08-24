import time
import threading
from collections import defaultdict
from fastapi import HTTPException, Request

# ── Simple In-Memory Limiter ──────────────────────────────────────────────────
# In production, use Redis. For now, this protects the dev environment.

class SimpleLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self.history = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str):
        now = time.time()
        minute_ago = now - 60

        with self._lock:
            timestamps = [t for t in self.history[key] if t > minute_ago]
            if timestamps:
                self.history[key] = timestamps
            else:
                self.history.pop(key, None)
                timestamps = []

            if len(timestamps) >= self.rpm:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded ({self.rpm} requests/min). Please wait a moment."
                )

            self.history[key].append(now)

# Global instances
chat_limiter = SimpleLimiter(requests_per_minute=12)  # 12 chat msgs per min
index_limiter = SimpleLimiter(requests_per_minute=3)   # 3 index ops per min
