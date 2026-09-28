from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

LEVEL_RE = re.compile(r"\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b")
ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL"}


@dataclass(frozen=True)
class ParsedLine:
    level: str
    is_error: bool


def parse_line(line: str) -> Optional[ParsedLine]:
    """Return the first log level found in the line, or None if there is none."""
    m = LEVEL_RE.search(line)
    if not m:
        return None
    level = m.group(1)
    return ParsedLine(level, level in ERROR_LEVELS)
