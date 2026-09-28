from __future__ import annotations
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class LogTailer:
    """Follows a growing file. watchdog triggers reads; read_new() can also be polled."""

    def __init__(self, path: str, on_line: Callable[[str], None], from_start: bool = False):
        self.path = Path(path).resolve()
        self.on_line = on_line
        self._lock = threading.Lock()
        self._buf = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._offset = 0 if from_start else self.path.stat().st_size
        self._observer = None

    def read_new(self) -> None:
        with self._lock:
            try:
                size = self.path.stat().st_size
            except FileNotFoundError:
                return
            if size < self._offset:          # truncated / rotated
                self._offset, self._buf = 0, ""
            if size == self._offset:
                return
            with open(self.path, "rb") as f:
                f.seek(self._offset)
                data = f.read()
                self._offset = f.tell()
            lines = (self._buf + data.decode("utf-8", errors="replace")).split("\n")
            self._buf = lines.pop()          # keep any partial last line
            for line in lines:
                if line.strip():
                    self.on_line(line.rstrip("\r"))

    def start(self) -> None:
        tailer = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if not event.is_directory and Path(event.src_path).resolve() == tailer.path:
                    tailer.read_new()

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
