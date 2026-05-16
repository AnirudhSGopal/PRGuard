import time
import threading
from collections import defaultdict
from fastapi import HTTPException, Request

# ── Simple In-Memory Limiter ──────────────────────────────────────────────────
# This protects the environment without requiring Redis.
# Tracks hits per unique key (IP address).

class SimpleLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self.history = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str):
        now = time.time()
        minute_ago = now - 60

        with self._lock:
            # Clean up old timestamps
            timestamps = [t for t in self.history[key] if t > minute_ago]
            if timestamps:
                self.history[key] = timestamps
            else:
                self.history.pop(key, None)
                timestamps = []

            if len(timestamps) >= self.rpm:
                # 429 handler in main.py will customize the message
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded ({self.rpm} requests/min)."
                )

            self.history[key].append(now)

# Global instances configured for production safety
login_limiter = SimpleLimiter(requests_per_minute=5)   # 5 login attempts per min per IP
auth_limiter = SimpleLimiter(requests_per_minute=10)   # 10 OAuth attempts per min per IP
chat_limiter = SimpleLimiter(requests_per_minute=20)   # 20 chat messages per min per IP
index_limiter = SimpleLimiter(requests_per_minute=3)   # 3 index ops per min per IP (heavy)
