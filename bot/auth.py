"""
Layer-2 access control — the load-bearing security gate (see design doc §Access control).

Every inbound message carries a Bot-Framework-verified AAD identity (aadObjectId) that cannot
be spoofed. Before the bot acts on ANYTHING (process a request OR approve prod), we check that
identity against the authorised-COMMs allowlist, implemented as membership of the AAD security
group `PTVI-Website-COMMs`. IT manages the roster in one place; no code change to add/remove people.

Resolution order:
  1. If COMMS_GROUP_ID is set  -> authoritative check via Microsoft Graph group membership,
     authenticating as the VM's managed identity (passwordless). Result cached briefly.
  2. Else fall back to COMMS_ALLOWLIST env (explicit object IDs) — PoC bootstrap only, logged loudly.

Fail CLOSED: any error resolving membership => denied. An LLM-driven agent must never act on an
unverified sender.
"""
from __future__ import annotations

import time
from typing import Optional

from config import Config

# Graph is optional at import time so the bot can start (and be tested) without azure libs
try:
    import requests as _http  # lightweight; used only for the Graph call
except Exception:  # noqa: BLE001
    _http = None

_GRAPH = "https://graph.microsoft.com/v1.0"
_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 300  # seconds


def _mi_token() -> Optional[str]:
    """
    Get a Graph token as the VM's system-assigned managed identity, via IMDS.
    No secret, no interactive login. Returns None if not on an Azure VM / IMDS unreachable.
    """
    if _http is None:
        return None
    try:
        r = _http.get(
            "http://169.254.169.254/metadata/identity/oauth2/token",
            params={"api-version": "2018-02-01", "resource": "https://graph.microsoft.com"},
            headers={"Metadata": "true"},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:  # noqa: BLE001
        pass
    return None


def _in_group_via_graph(aad_object_id: str, group_id: str) -> Optional[bool]:
    """
    True/False if resolvable, None on any error (caller fails closed).

    Uses GET /groups/{id}/members and checks the sender's object id against the returned
    member ids. This works with the managed identity's GroupMember.Read.All app permission
    (checkMemberGroups on another user's directoryObject would additionally require
    User.Read.All / Directory.Read.All, which we deliberately don't grant). Follows @odata
    paging so large groups are handled.
    """
    token = _mi_token()
    if not token or _http is None:
        return None
    try:
        url = f"{_GRAPH}/groups/{group_id}/members?$select=id&$top=999"
        headers = {"Authorization": f"Bearer {token}"}
        while url:
            r = _http.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                return None
            body = r.json()
            for m in body.get("value", []):
                if m.get("id") == aad_object_id:
                    return True
            url = body.get("@odata.nextLink")
        return False
    except Exception:  # noqa: BLE001
        return None


def is_authorised(aad_object_id: Optional[str]) -> tuple[bool, str]:
    """
    Returns (allowed, reason). `reason` is for the audit log, not shown verbatim to users.
    """
    if not aad_object_id:
        return False, "no verified sender identity on the activity"

    # cache
    hit = _cache.get(aad_object_id)
    if hit and (time.time() - hit[1]) < _CACHE_TTL:
        return hit[0], "cached"

    allowed = False
    reason = ""
    if Config.COMMS_GROUP_ID:
        res = _in_group_via_graph(aad_object_id, Config.COMMS_GROUP_ID)
        if res is None:
            # fail closed — do NOT fall through to the allowlist when a group IS configured
            return False, "graph membership unresolved (failing closed)"
        allowed, reason = res, f"graph group {Config.COMMS_GROUP_ID} membership={res}"
    elif Config.COMMS_ALLOWLIST:
        allowed = aad_object_id in Config.COMMS_ALLOWLIST
        reason = f"PoC allowlist membership={allowed} (COMMS_GROUP_ID unset)"
    else:
        # nothing configured at all => deny; refuse to run wide open
        return False, "no COMMS_GROUP_ID and no allowlist configured — denying"

    _cache[aad_object_id] = (allowed, time.time())
    return allowed, reason
