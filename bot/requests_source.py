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
