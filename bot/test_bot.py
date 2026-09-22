#!/usr/bin/env python3
"""
Tests for the bot's pure logic — intent parsing + Layer-2 auth fail-closed behaviour.
No Bot Framework SDK or network needed. Run:  python3 bot/test_bot.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import parse_intent  # noqa: E402


# ---- intent parsing ----
def test_process_plain():
    assert parse_intent("process the loker request").kind == "process"

def test_process_indonesian():
    assert parse_intent("tolong proses request ini").kind == "process"

def test_approve_button_value():
    i = parse_intent("", {"action": "approve_prod", "request_id": "abc-123"})
    assert i.kind == "approve_prod" and i.request_id == "abc-123" and i.target == "prod"

def test_approve_text():
    assert parse_intent("approve for prod").kind == "approve_prod"

def test_status():
    assert parse_intent("what's pending?").kind == "status"

def test_help():
    assert parse_intent("help").kind == "help"

def test_unknown():
    assert parse_intent("hello there").kind == "unknown"

def test_request_id_extraction():
    i = parse_intent("process request: my-news-2026")
    assert i.kind == "process" and i.request_id == "my-news-2026"


# ---- auth fail-closed ----
def test_auth_denies_when_nothing_configured():
    # ensure a clean env: no group, no allowlist
    os.environ.pop("PTVI_COMMS_GROUP_ID", None)
    os.environ.pop("PTVI_COMMS_ALLOWLIST", None)
    # reimport config+auth fresh so they pick up cleared env
    for m in ("config", "auth"):
        sys.modules.pop(m, None)
    import auth  # noqa: E402
    allowed, _ = auth.is_authorised("some-oid")
    assert allowed is False

def test_auth_denies_empty_sender():
    for m in ("config", "auth"):
        sys.modules.pop(m, None)
    import auth  # noqa: E402
    allowed, reason = auth.is_authorised(None)
    assert allowed is False and "no verified sender" in reason

def test_auth_allowlist_poc():
    os.environ["PTVI_COMMS_ALLOWLIST"] = "oid-1,oid-2"
    os.environ.pop("PTVI_COMMS_GROUP_ID", None)
    for m in ("config", "auth"):
        sys.modules.pop(m, None)
    import auth  # noqa: E402
    assert auth.is_authorised("oid-1")[0] is True
    assert auth.is_authorised("oid-3")[0] is False
    os.environ.pop("PTVI_COMMS_ALLOWLIST", None)


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(run())
