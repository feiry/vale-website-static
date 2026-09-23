"""
Request source — where the bot finds request folders to process.

Two backends, selected by config:
  - SharePoint (Graph) when PTVI_REQUEST_GROUP_ID is set — the production path. Reads the
    request library of the PTGDI Teams team, authenticating as the VM managed identity.
    resolve() DOWNLOADS the chosen request folder to a local scratch dir so the existing
    operator/intake scripts can run on real files.
  - Local folder (PTVI_REQUESTS_ROOT) otherwise — the PoC/dev path, laid out identically
    (<root>/1-Submitted/<request-folder>/...).

Both expose the same interface: list_submitted() -> [names], resolve(id) -> (id, local_path).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from config import Config

try:
    import requests as _http
except Exception:  # noqa: BLE001
    _http = None

SUBMITTED = "1-Submitted"
IN_PROGRESS = "2-In-Progress"
DONE = "3-Done-Deployed"

_GRAPH = "https://graph.microsoft.com/v1.0"
# scratch dir where SharePoint request folders are downloaded before processing
_SCRATCH = Path(os.path.expanduser("~/ptvi-bot/sp-requests"))


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #

def _use_sharepoint() -> bool:
    return bool(getattr(Config, "REQUEST_GROUP_ID", ""))


def _mi_token() -> Optional[str]:
    if _http is None:
        return None
    try:
        r = _http.get(
            "http://169.254.169.254/metadata/identity/oauth2/token",
            params={"api-version": "2018-02-01", "resource": "https://graph.microsoft.com"},
            headers={"Metadata": "true"}, timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:  # noqa: BLE001
        pass
    return None


_app_token_cache = {"tok": None, "exp": 0.0}


def _app_token() -> Optional[str]:
    """
    Graph token via the bot APP REGISTRATION's client credentials (id + secret from env).
    Used for WRITE ops (folder moves): app-registration tokens carry granted app-roles
    reliably, unlike managed-identity tokens (which propagate app-role changes flakily).
    Cached until ~1 min before expiry.
    """
    import time as _t
    if _http is None:
        return None
    if _app_token_cache["tok"] and _t.time() < _app_token_cache["exp"] - 60:
        return _app_token_cache["tok"]
    app_id = getattr(Config, "APP_ID", "")
    secret = getattr(Config, "APP_PASSWORD", "")
    tenant = getattr(Config, "APP_TENANTID", "")
    if not (app_id and secret and tenant):
        return None
    try:
        r = _http.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={"client_id": app_id, "client_secret": secret,
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"},
            timeout=10,
        )
        if r.status_code == 200:
            j = r.json()
            _app_token_cache["tok"] = j.get("access_token")
            _app_token_cache["exp"] = _t.time() + j.get("expires_in", 3600)
            return _app_token_cache["tok"]
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------- #
# Local backend
# --------------------------------------------------------------------------- #

def _local_root() -> Path:
    return Path(Config.REQUESTS_ROOT)


def _local_list() -> list[str]:
    d = _local_root() / SUBMITTED
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def _local_resolve(request_id: Optional[str]):
    submitted = _local_list()
    if request_id:
        if request_id in submitted:
            return request_id, _local_root() / SUBMITTED / request_id
        return None, None
    if len(submitted) == 1:
        return submitted[0], _local_root() / SUBMITTED / submitted[0]
    return None, None


# --------------------------------------------------------------------------- #
# SharePoint (Graph) backend
# --------------------------------------------------------------------------- #

def _sp_get(path: str) -> Optional[dict]:
    token = _mi_token()
    if not token or _http is None:
        return None
    try:
        r = _http.get(f"{_GRAPH}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return None


def _sp_list() -> list[str]:
    grp = Config.REQUEST_GROUP_ID
    data = _sp_get(f"/groups/{grp}/drive/root:/{SUBMITTED}:/children")
    if not data:
        return []
    return sorted(item["name"] for item in data.get("value", []) if "folder" in item)


def _sp_download_folder(request_id: str) -> Optional[Path]:
    """Download every file in 1-Submitted/<request_id>/ to a local scratch dir; return it."""
    grp = Config.REQUEST_GROUP_ID
    token = _mi_token()
    if not token or _http is None:
        return None
    listing = _sp_get(f"/groups/{grp}/drive/root:/{SUBMITTED}/{request_id}:/children")
    if not listing:
        return None
    dest = _SCRATCH / request_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for item in listing.get("value", []):
        if "file" not in item:
            continue  # PoC: flat request folders (no nested dirs)
        url = item.get("@microsoft.graph.downloadUrl")
        if not url:
            continue
        try:
            resp = _http.get(url, timeout=60)
            if resp.status_code == 200:
                (dest / item["name"]).write_bytes(resp.content)
        except Exception:  # noqa: BLE001
            return None
    return dest


def _sp_resolve(request_id: Optional[str]):
    submitted = _sp_list()
    if request_id:
        if request_id not in submitted:
            return None, None
    elif len(submitted) == 1:
        request_id = submitted[0]
    else:
        return None, None
    local = _sp_download_folder(request_id)
    return (request_id, local) if local else (None, None)


def _sp_find_folder(request_id: str, stages: list[str]) -> Optional[str]:
    """Return the first stage folder that currently contains request_id, else None."""
    grp = Config.REQUEST_GROUP_ID
    for st in stages:
        data = _sp_get(f"/groups/{grp}/drive/root:/{st}:/children")
        if data and any(i.get("name") == request_id and "folder" in i for i in data.get("value", [])):
            return st
    return None


def _sp_move(request_id: str, from_stage: str, to_stage: str) -> bool:
    """Move 1-Submitted/<id> → 2-In-Progress/<id> etc. via Graph PATCH parentReference.

    Uses the APP token (client-credentials) for the write — MI tokens don't reliably carry
    Files.ReadWrite.All. Reads (below) still use the MI.
    """
    grp = Config.REQUEST_GROUP_ID
    token = _app_token() or _mi_token()  # prefer app-cred for write; fall back to MI
    if not token or _http is None:
        return False
    # get the item id of the source folder and the destination parent id
    src = _sp_get(f"/groups/{grp}/drive/root:/{from_stage}/{request_id}")
    dst_parent = _sp_get(f"/groups/{grp}/drive/root:/{to_stage}")
    if not src or not dst_parent:
        return False
    try:
        r = _http.patch(
            f"{_GRAPH}/groups/{grp}/drive/items/{src['id']}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"parentReference": {"id": dst_parent["id"]}},
            timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Public interface
# --------------------------------------------------------------------------- #

def list_submitted() -> list[str]:
    return _sp_list() if _use_sharepoint() else _local_list()


def resolve(request_id: Optional[str]) -> tuple[Optional[str], Optional[Path]]:
    """
    Resolve a request to (request_id, local_path). For SharePoint, the folder is downloaded
    to a local scratch dir first. If request_id is omitted and exactly one submitted request
    exists, that one is used ("process the request").
    """
    return _sp_resolve(request_id) if _use_sharepoint() else _local_resolve(request_id)


# stage constants for callers
STAGE_SUBMITTED = SUBMITTED
STAGE_IN_PROGRESS = IN_PROGRESS
STAGE_DONE = DONE
_ALL_STAGES = [SUBMITTED, IN_PROGRESS, DONE]


def move_request(request_id: str, to_stage: str) -> bool:
    """
    Move a request folder to another stage (1-Submitted / 2-In-Progress / 3-Done-Deployed).
    Idempotent: if it's already in to_stage, returns True. Best-effort — returns False on failure
    so callers can warn without failing the whole operation. Local mode moves the on-disk folder.
    """
    if to_stage not in _ALL_STAGES:
        return False
    if _use_sharepoint():
        cur = _sp_find_folder(request_id, _ALL_STAGES)
        if cur is None:
            return False
        if cur == to_stage:
            return True
        return _sp_move(request_id, cur, to_stage)
    # local mode
    root = _local_root()
    for st in _ALL_STAGES:
        src = root / st / request_id
        if src.is_dir():
            if st == to_stage:
                return True
            dst = root / to_stage / request_id
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))
            return True
    return False
