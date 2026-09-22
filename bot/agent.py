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
# grab an explicit request id if the user typed one (folder-name-ish token).
# The keyword must be a WHOLE word (\b after it) so "request" isn't read as "req"+"uest".
# We accept an id either after an explicit "id:"/"request #" separator, OR a token that
# actually looks like a folder id (contains a hyphen/dot/digit — not a plain English word).
_RID_LABELLED = re.compile(r"\b(?:request|req|folder|loker|id)\b\s*[:#]\s*([A-Za-z0-9._\-]{3,})", re.I)
_RID_SLUGLIKE = re.compile(r"\b([a-z0-9]+(?:[-.][a-z0-9]+){1,}[A-Za-z0-9._\-]*)", re.I)
# never treat these as an id if they slip through
_RID_STOP = {"the", "this", "that", "request", "req", "folder", "loker", "please", "tolong", "ini"}


def _extract_rid(t: str) -> Optional[str]:
    m = _RID_LABELLED.search(t)
    if m and m.group(1).lower() not in _RID_STOP:
        return m.group(1)
    # a slug-like token (has a hyphen/dot, e.g. "sample-news-demo") is very likely the id
    m = _RID_SLUGLIKE.search(t)
    if m and m.group(1).lower() not in _RID_STOP:
        return m.group(1)
    return None


def parse_intent(text: str, value: Optional[dict] = None) -> Intent:
    # 1) Adaptive Card button submissions arrive as `value`, not text — trust them first.
    if value and isinstance(value, dict) and value.get("action") == "approve_prod":
        return Intent(kind="approve_prod", request_id=value.get("request_id"), target="prod")

    t = (text or "").strip()
    if not t:
        return Intent(kind="unknown")

    rid = _extract_rid(t)

    if _APPROVE.search(t):
        return Intent(kind="approve_prod", request_id=rid, target="prod")
    if _PROCESS.search(t):
        return Intent(kind="process", request_id=rid, target="dev")
    if _STATUS.search(t):
        return Intent(kind="status", request_id=rid)
    if _HELP.search(t):
        return Intent(kind="help")
    return Intent(kind="unknown", request_id=rid)
