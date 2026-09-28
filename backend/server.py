from __future__ import annotations
import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.alerts import AlertPublisher
from backend.config import Config
from backend.detector import AnomalyDetector
from backend.parser import parse_line
from backend.tailer import LogTailer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("server")

cfg = Config.from_env()
detector = AnomalyDetector(cfg.window_seconds, cfg.min_events, cfg.warmup_samples,
                           cfg.sample_interval, cfg.alpha, cfg.min_std, cfg.min_delta)
publisher = AlertPublisher(cfg)
alerts: deque = deque(maxlen=200)     # newest first
history: deque = deque(maxlen=120)    # recent stats snapshots for the chart
clients: set = set()
_tasks: set = set()
_loop: asyncio.AbstractEventLoop | None = None


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def broadcast(msg: dict) -> None:
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:  # noqa: BLE001
            clients.discard(ws)


def handle_alert(alert) -> None:
    d = alert.to_dict()
    alerts.appendleft(d)
    log.info("ALERT %s %s: %s", d["status"], d["severity"], d["message"])
    _spawn(broadcast({"type": "alert", "alert": d}))
    _spawn(asyncio.to_thread(publisher.publish, d))


def on_line(line: str) -> None:
    parsed = parse_line(line)
    if parsed is None:
        return
    alert = detector.process(time.time(), parsed.is_error)
    if alert and _loop:
        _loop.call_soon_threadsafe(handle_alert, alert)


def state() -> dict:
    return {"alerts": list(alerts), "history": list(history), "stats": detector.snapshot()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    tailer = LogTailer(cfg.log_file, on_line, cfg.from_start)
    tailer.start()
    log.info("Tailing %s | AWS publishing: %s", tailer.path, "on" if publisher.enabled else "off")

    async def ticker():
        while True:
            await asyncio.sleep(1)
            try:
                tailer.read_new()  # safety net in case FS events are missed
                alert = detector.tick(time.time())
                if alert:
                    handle_alert(alert)
                snap = detector.snapshot()
                snap["ts"] = time.time()
                history.append(snap)
                await broadcast({"type": "stats", "stats": snap})
            except Exception:  # noqa: BLE001
                log.exception("ticker error")

    task = asyncio.create_task(ticker())
    yield
    task.cancel()
    tailer.stop()


app = FastAPI(title="Log Anomaly Detector", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True, "log_file": cfg.log_file, "aws": publisher.enabled}


@app.get("/api/state")
def get_state():
    return state()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json({"type": "init", **state()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
