"""
Request source — where the bot finds request folders to process.

For the PoC this is a local directory on the VM (PTVI_REQUESTS_ROOT), laid out like the
SharePoint library: <root>/1-Submitted/<request-folder>/... . In production the same interface
is backed by Microsoft Graph reads of the PTGDI SharePoint library; only this module changes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from config import Config

SUBMITTED = "1-Submitted"
IN_PROGRESS = "2-In-Progress"
DONE = "3-Done-Deployed"


def _root() -> Path:
    return Path(Config.REQUESTS_ROOT)


def list_submitted() -> list[str]:
    d = _root() / SUBMITTED
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def resolve(request_id: Optional[str]) -> tuple[Optional[str], Optional[Path]]:
    """
    Resolve a request folder. If request_id is given, find that folder; if omitted and exactly
    one submitted request exists, use it (the common "process the loker request" case).
    Returns (request_id, path) or (None, None) with the caller reporting the ambiguity.
    """
    submitted = list_submitted()
    if request_id:
        if request_id in submitted:
            return request_id, _root() / SUBMITTED / request_id
        return None, None
    if len(submitted) == 1:
        rid = submitted[0]
        return rid, _root() / SUBMITTED / rid
    return None, None
