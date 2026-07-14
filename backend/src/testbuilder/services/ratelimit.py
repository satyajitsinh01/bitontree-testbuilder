"""Sliding-window rate limiting (FR-067). In-process fallback for dev/tests;
production points this at Redis (same key scheme, INCR+EXPIRE)."""

import time
from collections import defaultdict, deque

_windows: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_sec: int = 60) -> bool:
    now = time.monotonic()
    window = _windows[key]
    while window and window[0] <= now - window_sec:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def count(key: str) -> int:
    return len(_windows[key])


def reset_for_tests() -> None:
    _windows.clear()
