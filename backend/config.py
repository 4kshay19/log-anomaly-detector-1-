from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional


def _env(name, default, cast=str):
    v = os.getenv(name)
    return cast(v) if v not in (None, "") else default


@dataclass(frozen=True)
class Config:
    log_file: str = "logs/app.log"
    window_seconds: float = 30.0   # sliding window length
    min_events: int = 10           # ignore windows with fewer lines
    warmup_samples: int = 20       # samples used to learn the baseline
    sample_interval: float = 1.0   # seconds between baseline/detect samples
    alpha: float = 0.02            # EWMA smoothing for baseline drift
    min_std: float = 0.015         # floor on baseline std-dev (error-rate units)
    min_delta: float = 0.05        # min absolute rise over baseline to alert
    from_start: bool = False       # read existing file content on startup
    aws_region: Optional[str] = None
    cw_log_group: Optional[str] = None
    cw_log_stream: str = "anomaly-alerts"
    sns_topic_arn: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            log_file=_env("LOG_FILE", cls.log_file),
            window_seconds=_env("WINDOW_SECONDS", cls.window_seconds, float),
            min_events=_env("MIN_EVENTS", cls.min_events, int),
            warmup_samples=_env("WARMUP_SAMPLES", cls.warmup_samples, int),
            sample_interval=_env("SAMPLE_INTERVAL", cls.sample_interval, float),
            alpha=_env("BASELINE_ALPHA", cls.alpha, float),
            min_std=_env("MIN_STD", cls.min_std, float),
            min_delta=_env("MIN_DELTA", cls.min_delta, float),
            from_start=_env("FROM_START", "0") in ("1", "true", "True"),
            aws_region=_env("AWS_REGION", None),
            cw_log_group=_env("CLOUDWATCH_LOG_GROUP", None),
            cw_log_stream=_env("CLOUDWATCH_LOG_STREAM", cls.cw_log_stream),
            sns_topic_arn=_env("SNS_TOPIC_ARN", None),
        )
