#!/usr/bin/env python3
"""
Tests for the operator pipeline. These run WITHOUT any cloud access and (for detection)
without the site/ mirror. Run:  python3 operator/test_operator.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_svc as op  # noqa: E402


def _mk(folder: Path, filename: str, payload: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / filename
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_detect_news():
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "my-article-news.json", {"slug": "x"})
        t, p = op.detect_type(Path(d))
        assert t == "news", t
        assert p.name == "my-article-news.json"


def test_detect_doc():
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "report-doc.json", {"title": "x"})
        t, _ = op.detect_type(Path(d))
        assert t == "documents", t


def test_detect_vacancy():
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "vacancies.json", {"add": []})
        t, _ = op.detect_type(Path(d))
        assert t == "vacancy", t


def test_detect_awards():
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "2026-award.json", {"link": ""})
        t, _ = op.detect_type(Path(d))
        assert t == "awards", t


def test_detect_ambiguous_returns_none():
    # two different types in one folder -> refuse to guess
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "a-news.json", {})
        _mk(Path(d), "b-doc.json", {})
        t, _ = op.detect_type(Path(d))
        assert t is None


def test_detect_empty_returns_none():
    with tempfile.TemporaryDirectory() as d:
        t, _ = op.detect_type(Path(d))
        assert t is None


def test_process_bad_target():
    with tempfile.TemporaryDirectory() as d:
        r = op.process("r1", d, target="staging")
        assert r.ok is False
        assert "invalid target" in r.message


def test_process_missing_folder():
    r = op.process("r1", "/no/such/folder", target="dev")
    assert r.ok is False
    assert "not found" in r.message


def test_process_undetectable_fails_cleanly():
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "random.json", {})  # matches no type
        r = op.process("r1", d, target="dev")
        assert r.ok is False
        assert r.request_type is None
        assert any(s.stage == op.Stage.DETECT and s.status == op.Status.FAILED for s in r.stages)


def test_lock_blocks_second_writer():
    # hold the lock, then a process() call must fail fast with a busy message
    with tempfile.TemporaryDirectory() as d:
        _mk(Path(d), "x-news.json", {"slug": "x"})
        with op._Lock(op.LOCK_PATH, "holder"):
            r = op.process("r2", d, target="dev")
        assert r.ok is False
        assert "busy" in r.message.lower()


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(run())
