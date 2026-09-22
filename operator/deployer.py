"""
Deployer — the deploy+verify step the operator calls (the pluggable `deployer` callable).

Publishes the built site to blob static-website storage as the VM's MANAGED IDENTITY
(no secret, no interactive login — `az login --identity` must already be active on the VM),
then verifies each changed URL serves HTTP 200 with expected content.

PoC target = PTGDI storage (stptviwebbotpoc). Swapping to Vale's stidstaticsite002 later is a
config change (account name + web base), not a code change — same managed-identity auth path,
once the Vale RBAC grant lands.

Design contract: deployer(target, result) -> StageResult   (imported names from operator_svc)

Incremental by design (see [deploy_incremental] memory): uploads only the files changed by this
run, never a full sync. The set of changed files is derived from the intake/build output URLs
plus any freshly written article pages under the run window.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError


# --- PoC config (swap these two for Vale dev when the grant lands) --------------------------
DEV_ACCOUNT = "stptviwebbotpoc"
DEV_WEB_BASE = "https://stptviwebbotpoc.z23.web.core.windows.net"
PROD_ACCOUNT = "stidstaticsiteprod"   # not used in PoC; here for later
PROD_WEB_BASE = "https://www.valeindonesia.com"

SITE_ROOT_REL = Path("site") / "vale.com"   # relative to repo root
CONTAINER = "$web"


def _target_cfg(target: str) -> tuple[str, str]:
    return (PROD_ACCOUNT, PROD_WEB_BASE) if target == "prod" else (DEV_ACCOUNT, DEV_WEB_BASE)


def _az_upload(account: str, local: Path, blob_name: str) -> tuple[bool, str]:
    """Upload one file to $web as the managed identity. Returns (ok, detail)."""
    cp = subprocess.run(
        ["az", "storage", "blob", "upload",
         "--account-name", account, "--auth-mode", "login",
         "--container-name", CONTAINER, "--name", blob_name,
         "--file", str(local), "--overwrite", "--only-show-errors"],
        capture_output=True, text=True, timeout=120,
    )
    return cp.returncode == 0, (cp.stderr or cp.stdout).strip()[-300:]


def _verify_url(url: str, needle: Optional[str] = None, tries: int = 3) -> tuple[bool, str]:
    """GET url; ok if 200 (and, if given, needle present in body). Retries for propagation."""
    last = ""
    for i in range(tries):
        try:
            with urlopen(url, timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                if r.status == 200 and (needle is None or needle in body):
                    return True, f"200{' + content' if needle else ''}"
                last = f"HTTP {r.status}" + ("" if needle is None or needle in body else " (needle missing)")
        except HTTPError as e:
            last = f"HTTP {e.code}"
        except URLError as e:
            last = f"urlerror {e.reason}"
        time.sleep(2 * (i + 1))
    return False, last


def make_deployer(repo_root: Path, changed_files: list[tuple[Path, str]],
                  verify_urls: list[tuple[str, Optional[str]]]):
    """
    Build a deployer(target, result) closure.

    changed_files : list of (local_path, blob_name) to upload — the incremental change set.
    verify_urls   : list of (url, needle) to check after upload. `url` here is the PATH part
                    (e.g. '/indonesia/w/foo.html'); the web base is prefixed per target.
    """
    # import here to avoid a circular import at module load
    from operator_svc import StageResult, Stage, Status

    def deployer(target: str, result) -> "StageResult":
        account, web_base = _target_cfg(target)

        # 1) upload the change set
        uploaded, failures = 0, []
        for local, blob in changed_files:
            if not local.is_file():
                failures.append(f"missing local file: {local}")
                continue
            ok, detail = _az_upload(account, local, blob)
            if ok:
                uploaded += 1
            else:
                failures.append(f"{blob}: {detail}")
        if failures:
            return StageResult(Stage.DEPLOY, Status.FAILED,
                               detail=f"uploaded {uploaded}, {len(failures)} failed: " + "; ".join(failures[:3]))

        # 2) verify each changed URL serves 200 (+content when we have a needle)
        bad = []
        for path, needle in verify_urls:
            url = web_base + path
            ok, detail = _verify_url(url, needle)
            if not ok:
                bad.append(f"{url} -> {detail}")
        if bad:
            return StageResult(Stage.VERIFY, Status.FAILED,
                               detail=f"deployed {uploaded} file(s) but verify failed: " + "; ".join(bad[:3]))

        return StageResult(Stage.DEPLOY, Status.OK,
                           detail=f"uploaded {uploaded} file(s) to {account}/$web, verified {len(verify_urls)} URL(s)")

    return deployer
