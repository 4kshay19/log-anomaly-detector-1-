# Real-Time Log Anomaly Detector

Tails a growing log file, computes a sliding-window error rate, learns a baseline, scores deviations
(z-score → LOW / MEDIUM / HIGH / CRITICAL), streams alerts to a React dashboard over WebSockets
(polling fallback), and pushes them to AWS CloudWatch Logs and/or SNS.

```
log file ──watchdog──▶ parser ──▶ detector ──▶ FastAPI ──WebSocket──▶ React UI
                                     └────────────────▶ CloudWatch Logs / SNS
```

## Run (3 terminals)

```bash
pip install -r requirements.txt

# 1. backend (from project root)
uvicorn backend.server:app --port 8000

# 2. simulated log traffic (normal ~3% errors, bursts of rising severity)
python scripts/generate_logs.py

# 3. frontend
cd frontend && npm install && npm run dev      # open http://localhost:5173
```

The baseline learns for ~50 s (a full 30 s window plus 20 samples) and the first burst hits at ~75 s. Alerts escalate as the window fills,
then a RESOLVED alert appears when the rate returns to normal.

Single-port mode: `cd frontend && npm run build`, then open http://localhost:8000 (the backend serves `frontend/dist`).

Monitor your own log: `LOG_FILE=/var/log/myapp.log uvicorn backend.server:app`.
Lines need a level token such as `ERROR`, `WARN`, `INFO`; `ERROR`/`CRITICAL`/`FATAL` count as errors.

## Configuration (env vars)

| Variable | Default | Meaning |
|---|---|---|
| `LOG_FILE` | `logs/app.log` | file to monitor |
| `WINDOW_SECONDS` | 30 | sliding window |
| `WARMUP_SAMPLES` | 20 | samples to learn baseline |
| `MIN_EVENTS` | 10 | min lines in window before evaluating |
| `MIN_STD` / `MIN_DELTA` | 0.015 / 0.05 | noise floors (error-rate units) |
| `FROM_START` | 0 | set `1` to process existing file content |
| `AWS_REGION` | – | region for boto3 |
| `CLOUDWATCH_LOG_GROUP` / `CLOUDWATCH_LOG_STREAM` | – / `anomaly-alerts` | created if missing |
| `SNS_TOPIC_ARN` | – | firing alerts are published here |

## AWS

Set credentials as usual (`aws configure` or env vars) plus the variables above. IAM needs
`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` and `sns:Publish`.
CloudWatch receives firing and resolved alerts; SNS receives firing alerts only.
Failures are logged and never crash the app.

## Detection logic

Severity by z-score `(rate − baseline) / std`: LOW ≥ 3, MEDIUM ≥ 5, HIGH ≥ 8, CRITICAL ≥ 12, and the rate
must also exceed the baseline by `MIN_DELTA`. The baseline updates (EWMA) only on normal samples so
incidents don't get absorbed. Alerts fire on onset and on escalation; hysteresis prevents flapping.

## Tests

```bash
pytest
```
