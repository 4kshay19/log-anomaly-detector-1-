from __future__ import annotations
import math
import threading
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class Alert:
    id: int
    timestamp: float
    status: str            # "firing" | "resolved"
    severity: str
    error_rate: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    window_events: int
    window_errors: int
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


class AnomalyDetector:
    """Sliding-window error-rate detector with a learned, slowly drifting baseline.

    1. Warm-up (once the window is full): the first `warmup_samples` rate samples define mean/std.
    2. Afterwards each sample gets a z-score against the baseline.
    3. z >= thresholds -> severity LOW / MEDIUM / HIGH / CRITICAL.
    4. The baseline only adapts (EWMA) on normal samples, so anomalies don't poison it.
    """

    def __init__(self, window_seconds=30.0, min_events=10, warmup_samples=30,
                 sample_interval=1.0, alpha=0.02, min_std=0.015, min_delta=0.05,
                 thresholds=(3.0, 5.0, 8.0, 12.0)):
        self.window = window_seconds
        self.min_events = min_events
        self.warmup_samples = warmup_samples
        self.sample_interval = sample_interval
        self.alpha = alpha
        self.min_std = min_std
        self.min_delta = min_delta
        self.thresholds = thresholds
        self._lock = threading.RLock()
        self._events: deque = deque()   # (timestamp, is_error)
        self._errors = 0
        self._warmup: list = []
        self._mean = 0.0
        self._var = 0.0
        self._ready = False
        self._last_sample: Optional[float] = None
        self._current: Optional[str] = None
        self._next_id = 1
        self._first_ts: Optional[float] = None

    # ---- public API -------------------------------------------------------
    def process(self, ts: float, is_error: bool) -> Optional[Alert]:
        with self._lock:
            if self._first_ts is None:
                self._first_ts = ts
            self._events.append((ts, bool(is_error)))
            if is_error:
                self._errors += 1
            self._prune(ts)
            return self._check(ts)

    def tick(self, ts: float) -> Optional[Alert]:
        """Call periodically so the window drains and alerts resolve when logs go quiet."""
        with self._lock:
            self._prune(ts)
            return self._check(ts)

    def snapshot(self) -> dict:
        with self._lock:
            total = len(self._events)
            rate = self._errors / total if total else 0.0
            std = self._std()
            return {
                "ts": self._last_ts(),
                "rate": rate,
                "mean": self._mean if self._ready else None,
                "std": std if self._ready else None,
                "threshold": self._mean + self.thresholds[0] * std if self._ready else None,
                "events": total,
                "errors": self._errors,
                "ready": self._ready,
                "warmup": min(1.0, len(self._warmup) / self.warmup_samples),
                "severity": self._current,
            }

    # ---- internals --------------------------------------------------------
    def _last_ts(self) -> float:
        return self._events[-1][0] if self._events else 0.0

    def _std(self) -> float:
        return max(math.sqrt(self._var), self.min_std)

    def _prune(self, ts: float) -> None:
        cutoff = ts - self.window
        while self._events and self._events[0][0] <= cutoff:
            _, was_err = self._events.popleft()
            if was_err:
                self._errors -= 1

    def _classify(self, z: float, delta: float) -> Optional[str]:
        if delta < self.min_delta:
            return None
        sev = None
        for name, t in zip(SEVERITIES, self.thresholds):
            if z >= t:
                sev = name
        return sev

    def _check(self, ts: float) -> Optional[Alert]:
        total = len(self._events)
        if total < self.min_events:
            return self._resolve(ts, 0.0, total, 0.0) if self._current else None
        if self._last_sample is not None and ts - self._last_sample < self.sample_interval:
            return None
        self._last_sample = ts
        rate = self._errors / total

        if not self._ready:
            if self._first_ts is None or ts - self._first_ts < self.window:
                return None  # learn only from a fully populated window
            self._warmup.append(rate)
            if len(self._warmup) >= self.warmup_samples:
                self._mean = float(np.mean(self._warmup))
                self._var = float(np.var(self._warmup))
                self._ready = True
            return None

        z = (rate - self._mean) / self._std()
        sev = self._classify(z, rate - self._mean)
        if sev is None:
            if self._current and z >= self.thresholds[0] * 0.6:
                return None  # hysteresis: still elevated, avoid flapping
            d = rate - self._mean
            self._mean += self.alpha * d
            self._var = (1 - self.alpha) * (self._var + self.alpha * d * d)
            return self._resolve(ts, rate, total, z) if self._current else None

        prev, self._current = self._current, sev
        if prev is None or SEVERITIES.index(sev) > SEVERITIES.index(prev):
            msg = (f"Error rate {rate:.1%} is {z:.1f}σ above baseline {self._mean:.1%} "
                   f"({self._errors}/{total} lines in last {self.window:g}s)")
            return self._make(ts, "firing", sev, rate, z, total, msg)
        return None

    def _resolve(self, ts, rate, total, z) -> Alert:
        sev, self._current = self._current, None
        msg = f"Error rate back to normal ({rate:.1%}, baseline {self._mean:.1%})"
        return self._make(ts, "resolved", sev, rate, z, total, msg)

    def _make(self, ts, status, sev, rate, z, total, msg) -> Alert:
        a = Alert(self._next_id, ts, status, sev, rate, self._mean, self._std(),
                  z, total, self._errors, msg)
        self._next_id += 1
        return a
