from backend.detector import AnomalyDetector, SEVERITIES


def make():
    return AnomalyDetector(window_seconds=10, min_events=5, warmup_samples=10, sample_interval=1.0)


def feed(det, start, seconds, per_sec=50, err_rate=0.02):
    out, n_err = [], round(per_sec * err_rate)
    for s in range(seconds):
        for i in range(per_sec):
            a = det.process(start + s + i / per_sec, i < n_err)
            if a:
                out.append(a)
    return out


def test_no_alerts_during_warmup():
    det = make()
    assert feed(det, 0, 5, err_rate=0.5) == []
    assert not det.snapshot()["ready"]


def test_normal_traffic_is_quiet():
    det = make()
    assert feed(det, 0, 60) == []
    snap = det.snapshot()
    assert snap["ready"] and abs(snap["mean"] - 0.02) < 0.005


def test_spike_fires_escalating_then_resolves():
    det = make()
    feed(det, 0, 40)
    fired = feed(det, 40, 20, err_rate=0.4)
    assert fired and all(a.status == "firing" for a in fired)
    ranks = [SEVERITIES.index(a.severity) for a in fired]
    assert ranks == sorted(ranks) and fired[-1].severity == "CRITICAL"
    recovered = feed(det, 60, 30)
    assert recovered[-1].status == "resolved"
    assert det.snapshot()["severity"] is None


def test_too_few_events_ignored():
    det = AnomalyDetector(min_events=100, warmup_samples=3)
    assert feed(det, 0, 20, per_sec=2, err_rate=0.5) == []
