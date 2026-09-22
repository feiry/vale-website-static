"""
The "conversation brain" seam.

The design has a Claude agent decide WHICH request and WHEN to act, then call the deterministic
operator. For the PoC this is a small deterministic intent parser with the SAME interface the
Claude agent will have — so we can swap in the real agent later without touching bot logic.

parse_intent(text, value) -> Intent
  Intent.kind in {process, approve_prod, status, help, unknown}
  Intent.request_id : which request, if the user named one

Keeping this a pure function makes it trivially testable and keeps the LLM (when added) out of
the deploy path — it only ever produces an Intent; the operator does the work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Intent:
    kind: str                      # process | approve_prod | status | help | unknown
    request_id: Optional[str] = None
    target: str = "dev"


_PROCESS = re.compile(r"\b(process|publish|build|deploy|jalankan|proses)\b", re.I)
_APPROVE = re.compile(r"\b(approve|setuju|go\s*live|deploy\s+prod|to\s+prod|ke\s+prod)\b", re.I)
_STATUS = re.compile(r"\b(status|pending|what.?s\s+pending|antrian|apa\s+yang)\b", re.I)
_HELP = re.compile(r"\b(help|bantuan|what\s+can\s+you|commands?)\b", re.I)
# grab an explicit request id if the user typed one (folder-name-ish token)
_RID = re.compile(r"\b(?:request|req|folder|loker|id)\s*[:#]?\s*([A-Za-z0-9._\-]{3,})", re.I)


def parse_intent(text: str, value: Optional[dict] = None) -> Intent:
    # 1) Adaptive Card button submissions arrive as `value`, not text — trust them first.
    if value and isinstance(value, dict) and value.get("action") == "approve_prod":
        return Intent(kind="approve_prod", request_id=value.get("request_id"), target="prod")

    t = (text or "").strip()
    if not t:
        return Intent(kind="unknown")

    rid_match = _RID.search(t)
    rid = rid_match.group(1) if rid_match else None

    if _APPROVE.search(t):
        return Intent(kind="approve_prod", request_id=rid, target="prod")
    if _PROCESS.search(t):
        return Intent(kind="process", request_id=rid, target="dev")
    if _STATUS.search(t):
        return Intent(kind="status", request_id=rid)
    if _HELP.search(t):
        return Intent(kind="help")
    return Intent(kind="unknown", request_id=rid)
