from backend.parser import parse_line
from backend.tailer import LogTailer


def test_parse():
    assert parse_line("2026-01-01T00:00:00 ERROR auth boom").is_error
    assert not parse_line("2026-01-01T00:00:00 INFO auth ok").is_error
    assert parse_line("no level here") is None


def test_tailer_handles_partial_lines_and_truncation(tmp_path):
    f = tmp_path / "app.log"
    got = []
    t = LogTailer(str(f), got.append)
    with open(f, "a") as fh:
        fh.write("a\nb\npart")
    t.read_new()
    assert got == ["a", "b"]
    with open(f, "a") as fh:
        fh.write("ial\n")
    t.read_new()
    assert got[-1] == "partial"
    f.write_text("x\n")            # truncation/rotation
    t.read_new()
    assert got[-1] == "x"
