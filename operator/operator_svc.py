#!/usr/bin/env python3
"""
Operator service — deterministic, auditable pipeline for the PTVI website-support bot.

This is the "no-LLM" half of the design (see docs/plans/2026-09-15-teams-pipeline-vm-design.md).
The Teams bot / Claude agent decides WHEN to call this; the operator does the actual work
in a fixed, verifiable sequence:

    read request folder  ->  detect type  ->  dry-run  ->  apply  ->  build  ->  (deploy)  ->  verify

Everything here is a thin, honest wrapper over the EXISTING repo scripts
(intake-to-*.py, build-*.py). Those scripts already validate, back up, self-check, and are
dry-run-first; the operator's job is to orchestrate them, gate on their exit codes, hold a
single-writer lock, and return a structured, loggable result. No script behaviour is
reimplemented here.

Deploy + verify (the Vale-storage tail) are intentionally pluggable and default to a no-op
"planned" state until the cross-tenant storage grant lands — the detect/dry-run/apply/build
core is fully testable without any cloud access.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# Paths & config
# --------------------------------------------------------------------------- #

# The operator lives at <repo>/operator/operator.py, so the repo root is one up.
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / ".operator.lock"
AUDIT_LOG = REPO_ROOT / "operator-audit.log"
# Rollback manifests: one JSON per successful deploy, newest wins. Lets `rollback` undo the
# last processed request (restore data file, rebuild, delete the deployed blobs).
ROLLBACK_DIR = REPO_ROOT / ".operator-rollback"

# Which intake script + follow-on build handles each request type, and how the type is
# detected from the request folder. Detection is by the request JSON filename suffix,
# matching what COMMs' forms already emit.
#
#   *-news.json / news-record.json  -> news
#   *-doc.json  / doc-record.json   -> documents
#   *vacanc*.json / vacancies.json  -> vacancy
#   *award*.json                    -> awards
TYPE_SPECS = {
    "news": {
        "intake": "intake-to-news.py",
        "build": "build-news.py",
        "match": lambda n: n.endswith("-news.json") or n == "news-record.json",
    },
    "documents": {
        "intake": "intake-to-doc.py",
        "build": "build-doc-library.py",
        "match": lambda n: n.endswith("-doc.json") or n == "doc-record.json",
    },
    "vacancy": {
        "intake": "intake-to-vacancy.py",
        "build": None,  # vacancy intake regenerates the page itself; no separate build step
        "match": lambda n: "vacanc" in n and n.endswith(".json"),
    },
    "awards": {
        "intake": "intake-to-awards.py",
        "build": None,  # awards inject directly into the page HTML; no data-file build
        "match": lambda n: "award" in n and n.endswith(".json"),
    },
}


class Stage(str, Enum):
    DETECT = "detect"
    DRY_RUN = "dry_run"
    APPLY = "apply"
    BUILD = "build"
    DEPLOY = "deploy"
    VERIFY = "verify"


class Status(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    PLANNED = "planned"  # deploy/verify not wired yet (awaiting Vale storage grant)


# --------------------------------------------------------------------------- #
# Result types (structured, JSON-serialisable — this is what the bot posts back)
# --------------------------------------------------------------------------- #

@dataclass
class StageResult:
    stage: str
    status: str
    exit_code: Optional[int] = None
    detail: str = ""
    # trimmed stdout/stderr — enough to diagnose, not enough to flood a Teams card
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass
class OperatorResult:
    request_id: str
    request_type: Optional[str]
    target: str
    ok: bool
    started_at: str
    finished_at: str = ""
    stages: list = field(default_factory=list)
    message: str = ""
    _deployed_paths: list = field(default_factory=list)  # set by _auto_deployer, for rollback manifest

    def to_json(self) -> str:
        d = asdict(self)
        d.pop("_deployed_paths", None)  # internal, not part of the reported result
        return json.dumps(d, ensure_ascii=False, indent=2)


class OperatorError(Exception):
    """Raised for operator-level failures (bad request, lock held, etc.)."""


# --------------------------------------------------------------------------- #
# Single-writer lock (the plan's "one request at a time")
# --------------------------------------------------------------------------- #

class _Lock:
    """
    Dirt-simple advisory lock: an O_EXCL lockfile holding the owning pid + request id.
    The operator is the single writer to the data files and the site tree; two concurrent
    applies would corrupt backups/records. This makes a second concurrent process fail fast
    and loudly rather than interleave.
    """

    def __init__(self, path: Path, request_id: str):
        self.path = path
        self.request_id = request_id
        self._fd = None

    def __enter__(self):
        try:
            self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                held = self.path.read_text().strip()
            except OSError:
                held = "(unreadable)"
            raise OperatorError(
                f"operator busy — lock held by {held}. One request at a time; try again shortly."
            )
        os.write(self._fd, f"pid={os.getpid()} request={self.request_id} at={_now()}".encode())
        return self

    def __exit__(self, *exc):
        if self._fd is not None:
            os.close(self._fd)
        try:
            self.path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail(text: str, n: int = 1500) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else "…" + text[-n:]


def _run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
    """Run a repo script, capturing output. Never raises on non-zero — caller gates on rc."""
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=900
    )


def detect_type(folder: Path) -> tuple[Optional[str], Optional[Path]]:
    """
    Find the request JSON in the folder and classify it. Returns (type, request_json_path).
    Detection is filename-suffix based, matching the forms' output. Ambiguity (two matching
    files, or none) returns (None, None) so the caller reports a clear error rather than
    guessing.
    """
    candidates = sorted(p for p in folder.glob("*.json") if p.is_file())
    matched: list[tuple[str, Path]] = []
    for p in candidates:
        name = p.name.lower()
        for tname, spec in TYPE_SPECS.items():
            if spec["match"](name):
                matched.append((tname, p))
                break
    # de-dupe by type: if exactly one type matched, take its (first) file
    types = {t for t, _ in matched}
    if len(types) == 1 and matched:
        return matched[0][0], matched[0][1]
    return None, None


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #

# listing pages the news build always refreshes (verify these too)
_NEWS_LISTINGS = [
    "/indonesia/all-news.html",
    "/in/indonesia/all-news.html",
]

# Fixed pages each type deploys. news is special (article path is dynamic, parsed from
# EN:/ID: output) + always-refreshed listings. The other three edit a fixed EN+ID page pair.
_TYPE_PAGES = {
    "news": _NEWS_LISTINGS,  # PLUS the dynamic article pages (added in _auto_deployer)
    "vacancy": ["/indonesia/career.html", "/in/indonesia/career.html"],
    "awards": ["/indonesia/awards-and-certifications.html",
               "/in/indonesia/penghargaan-dan-sertifikasi.html"],
    "documents": ["/indonesia/documents-and-reports.html",
                  "/in/indonesia/dokumen-dan-laporan.html"],
}

# data file per type (relative to repo root) — used for rollback snapshots.
# news/documents are data-driven (JSON → build). vacancy/awards mutate HTML directly, so their
# rollback snapshots the PAGES instead (see _snapshot_state).
_DATA_FILE = {
    "news": "site-data/news-indonesia.json",
    "documents": "site-data/documents.json",
}


def _snapshot_state(rtype: str) -> dict:
    """
    Snapshot pre-apply state for rollback. Returns {"data": <path|None>, "pages": {rel: path}}.
    - Data-driven types (news, documents): snapshot the JSON data file.
    - HTML-direct types (vacancy, awards): snapshot the EN+ID pages they edit (no data file).
    """
    ROLLBACK_DIR.mkdir(exist_ok=True)
    stamp = int(time.time() * 1000)
    snap = {"data": None, "pages": {}}
    rel = _DATA_FILE.get(rtype)
    if rel and (REPO_ROOT / rel).is_file():
        dst = ROLLBACK_DIR / f"pre-{rtype}-data-{stamp}.json"
        shutil.copy2(REPO_ROOT / rel, dst)
        snap["data"] = str(dst)
    if rtype in ("vacancy", "awards"):
        site_root = REPO_ROOT / "site" / "vale.com"
        for i, urlpath in enumerate(_TYPE_PAGES.get(rtype, [])):
            src = site_root / urlpath.lstrip("/")
            if src.is_file():
                dst = ROLLBACK_DIR / f"pre-{rtype}-page{i}-{stamp}.html"
                shutil.copy2(src, dst)
                snap["pages"][urlpath.lstrip("/")] = str(dst)
    return snap


def _record_key(rec: dict) -> Optional[str]:
    """Stable identity for a data-file record, for surgical targeted rollback."""
    if not isinstance(rec, dict):
        return None
    if rec.get("slug"):
        return f"slug={rec['slug']}"          # news
    if rec.get("id") is not None:
        return f"id={rec['id']}"              # documents
    return None


def _added_record_keys(rtype: str, data_snapshot: Optional[str]) -> list[str]:
    """
    Diff the pre-apply data snapshot against the current data file to find which record(s)
    this run added. Returns their stable keys (slug=… / id=…) for surgical removal on rollback.
    """
    rel = _DATA_FILE.get(rtype)
    if not rel or not data_snapshot or not Path(data_snapshot).is_file():
        return []
    cur_path = REPO_ROOT / rel
    if not cur_path.is_file():
        return []
    try:
        before = json.loads(Path(data_snapshot).read_text())
        after = json.loads(cur_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    before_keys = {_record_key(r) for r in before if isinstance(before, list)}
    added = []
    for r in (after if isinstance(after, list) else []):
        k = _record_key(r)
        if k and k not in before_keys:
            added.append(k)
    return added


def _write_rollback_manifest(request_id: str, rtype: str, target: str,
                             snapshot: dict, deployed_paths: list[str]) -> None:
    """Record what a successful run did, so `rollback` can undo it. Newest file = last run."""
    try:
        ROLLBACK_DIR.mkdir(exist_ok=True)
        manifest = {
            "at": _now(), "request_id": request_id, "type": rtype, "target": target,
            "data_file": _DATA_FILE.get(rtype),
            "data_snapshot": snapshot.get("data"),
            "page_snapshots": snapshot.get("pages", {}),  # rel -> snapshot path (vacancy/awards)
            "deployed_paths": deployed_paths,
            "added_keys": _added_record_keys(rtype, snapshot.get("data")),  # for surgical targeted undo
        }
        mf = ROLLBACK_DIR / f"run-{int(time.time()*1000)}.json"
        mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    except OSError:
        pass


def _auto_deployer(result: OperatorResult):
    """
    Build a type-aware deployer for the run's changed pages. Returns None if nothing to deploy.

    - news:      dynamic article pages (parsed from the intake's EN:/ID: output-URL lines)
                 + the always-refreshed all-news listings.
    - vacancy / awards / documents: a fixed EN+ID page pair (see _TYPE_PAGES).
    """
    import deployer as dep_mod

    site_root = REPO_ROOT / dep_mod.SITE_ROOT_REL
    rtype = result.request_type
    all_paths: list[str] = []

    if rtype == "news":
        # dynamic article paths from EN:/ID: output lines
        for st in result.stages:
            for line in (st.stdout_tail or "").splitlines():
                line = line.strip()
                if line.startswith(("EN:", "ID:")) and "/" in line:
                    all_paths.append(line.split(":", 1)[1].strip())
        all_paths += _NEWS_LISTINGS
    else:
        # fixed pages for vacancy / awards / documents
        all_paths = list(_TYPE_PAGES.get(rtype, []))

    # de-dupe, keep order, and only deploy files that actually exist on disk
    seen, kept = set(), []
    for p in all_paths:
        rel = p.lstrip("/")
        if p in seen:
            continue
        seen.add(p)
        if (site_root / rel).is_file():
            kept.append(p)
    if not kept:
        return None

    changed_files = [(site_root / p.lstrip("/"), p.lstrip("/")) for p in kept]
    verify_urls = [(p, None) for p in kept]
    # stash the deployed blob paths on the result so process() can record a rollback manifest
    result._deployed_paths = [p.lstrip("/") for p in kept]
    return dep_mod.make_deployer(REPO_ROOT, changed_files, verify_urls)


def process(request_id: str, folder: str | os.PathLike, target: str = "dev",
            apply: bool = True, deployer=None, deploy: bool = False) -> OperatorResult:
    """
    Run the deterministic pipeline for one request folder.

    request_id : opaque id for logging/audit (e.g. the SharePoint folder name)
    folder     : path to the request folder (already fetched locally by the caller)
    target     : "dev" or "prod" — controls where the deploy step publishes
    apply      : if False, stop after a successful dry-run (preview only, no writes)
    deployer   : optional callable(target, result) -> StageResult for the deploy step.
                 If None and deploy=True, one is auto-built from the run's output URLs
                 (see _auto_deployer). If None and deploy=False, deploy+verify report PLANNED.
    deploy     : if True, actually deploy+verify (needs `az login --identity` active + RBAC).

    Returns an OperatorResult; also appends a line to operator-audit.log.
    """
    started = _now()
    folder = Path(folder).resolve()
    result = OperatorResult(
        request_id=request_id, request_type=None, target=target,
        ok=False, started_at=started,
    )

    def finish(ok: bool, message: str) -> OperatorResult:
        result.ok = ok
        result.message = message
        result.finished_at = _now()
        _audit(result)
        return result

    if target not in ("dev", "prod"):
        return finish(False, f"invalid target '{target}' (want dev|prod)")
    if not folder.is_dir():
        return finish(False, f"request folder not found: {folder}")

    try:
        with _Lock(LOCK_PATH, request_id):
            # 1) DETECT ------------------------------------------------------
            rtype, req_json = detect_type(folder)
            if rtype is None:
                result.stages.append(StageResult(
                    Stage.DETECT, Status.FAILED,
                    detail=("could not classify request — need exactly one recognised "
                            "*-news.json / *-doc.json / *vacanc*.json / *award*.json in the folder"),
                ))
                return finish(False, "type detection failed")
            result.request_type = rtype
            spec = TYPE_SPECS[rtype]
            result.stages.append(StageResult(
                Stage.DETECT, Status.OK, detail=f"type={rtype} request={req_json.name}"
            ))

            intake = REPO_ROOT / spec["intake"]
            if not intake.is_file():
                result.stages.append(StageResult(
                    Stage.DETECT, Status.FAILED, detail=f"intake script missing: {intake}"))
                return finish(False, "intake script missing on host")

            # 2) DRY-RUN -----------------------------------------------------
            dr = _run(["python3", str(intake), str(req_json), "--dry-run"], cwd=REPO_ROOT)
            result.stages.append(StageResult(
                Stage.DRY_RUN, Status.OK if dr.returncode == 0 else Status.FAILED,
                exit_code=dr.returncode, stdout_tail=_tail(dr.stdout), stderr_tail=_tail(dr.stderr),
            ))
            if dr.returncode != 0:
                return finish(False, f"dry-run failed (rc={dr.returncode}) — nothing written")

            if not apply:
                return finish(True, f"dry-run OK for {rtype} (preview only; apply=False)")

            # 3) APPLY -------------------------------------------------------
            # snapshot pre-apply state BEFORE apply, so rollback can restore it (data file for
            # news/documents; the edited pages themselves for vacancy/awards)
            snapshot = _snapshot_state(rtype)
            ap = _run(["python3", str(intake), str(req_json)], cwd=REPO_ROOT)
            result.stages.append(StageResult(
                Stage.APPLY, Status.OK if ap.returncode == 0 else Status.FAILED,
                exit_code=ap.returncode, stdout_tail=_tail(ap.stdout), stderr_tail=_tail(ap.stderr),
            ))
            if ap.returncode != 0:
                # intake scripts self-restore their data file on failure; report and stop.
                return finish(False, f"apply failed (rc={ap.returncode}); intake auto-restored its data file")

            # 4) BUILD -------------------------------------------------------
            build_script = spec["build"]
            if build_script:
                bp = _run(["python3", str(REPO_ROOT / build_script)], cwd=REPO_ROOT)
                result.stages.append(StageResult(
                    Stage.BUILD, Status.OK if bp.returncode == 0 else Status.FAILED,
                    exit_code=bp.returncode, stdout_tail=_tail(bp.stdout), stderr_tail=_tail(bp.stderr),
                ))
                if bp.returncode != 0:
                    return finish(False, f"build failed (rc={bp.returncode}) — data applied but site not rebuilt; needs attention")
            else:
                result.stages.append(StageResult(
                    Stage.BUILD, Status.SKIPPED,
                    detail=f"{rtype} intake regenerates its page directly; no separate build",
                ))

            # 5) DEPLOY + 6) VERIFY -----------------------------------------
            if deployer is None and deploy:
                deployer = _auto_deployer(result)  # build change-set from the run's output URLs

            if deployer is None:
                result.stages.append(StageResult(
                    Stage.DEPLOY, Status.PLANNED,
                    detail=f"deploy to {target} not requested (deploy=False)"))
                result.stages.append(StageResult(
                    Stage.VERIFY, Status.PLANNED, detail="pass deploy=True to publish + verify"))
                return finish(True, f"{rtype} applied + built locally; deploy to {target} PLANNED (deploy=False)")

            dep = deployer(target, result)
            result.stages.append(dep)
            if dep.status != Status.OK:
                return finish(False, f"deploy to {target} failed: {dep.detail}")

            # record a rollback manifest so `rollback` can undo this run
            if result._deployed_paths and (snapshot.get("data") or snapshot.get("pages")):
                _write_rollback_manifest(request_id, rtype, target, snapshot, result._deployed_paths)

            return finish(True, f"{rtype} deployed to {target} and verified")

    except OperatorError as e:
        result.stages.append(StageResult(Stage.DETECT, Status.FAILED, detail=str(e)))
        return finish(False, str(e))
    except subprocess.TimeoutExpired as e:
        result.stages.append(StageResult(Stage.BUILD, Status.FAILED, detail=f"timeout: {e}"))
        return finish(False, "a step timed out")


# --------------------------------------------------------------------------- #
# Rollback — undo the last processed request (restore data, rebuild, delete blobs)
# --------------------------------------------------------------------------- #

def _active_manifests() -> list[Path]:
    if not ROLLBACK_DIR.is_dir():
        return []
    return sorted(ROLLBACK_DIR.glob("run-*.json"))


def _select_manifest(request_id: Optional[str]) -> Optional[Path]:
    """Newest manifest overall, or the newest matching a specific request_id (targeted)."""
    runs = _active_manifests()
    if not runs:
        return None
    if request_id is None:
        return runs[-1]
    for mf in reversed(runs):  # newest matching first
        try:
            if json.loads(mf.read_text()).get("request_id") == request_id:
                return mf
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _remove_records_by_key(data_rel: str, keys: list[str]) -> int:
    """Surgically remove records whose key ∈ keys from the data file. Returns count removed."""
    p = REPO_ROOT / data_rel
    recs = json.loads(p.read_text())
    if not isinstance(recs, list):
        return 0
    keep = [r for r in recs if _record_key(r) not in set(keys)]
    removed = len(recs) - len(keep)
    if removed:
        p.write_text(json.dumps(keep, ensure_ascii=False, indent=2))
    return removed


def rollback(target: str = "dev", request_id: Optional[str] = None) -> dict:
    """
    Undo a processed request on `target`. Without request_id → the most recent run (LIFO).
    With request_id → that specific request, regardless of order (targeted).

    Data-driven types (news/documents) use SURGICAL removal: only that request's added
    record(s) are pulled from the data file (by slug/id), then rebuild — so newer same-type
    requests are preserved. HTML-direct types (vacancy/awards) restore the page snapshot
    (safe when it's the latest edit to those pages).
    Returns a structured result dict. Single-writer locked, like process().
    """
    started = _now()
    out = {"ok": False, "at": started, "message": "", "undid": None}

    def done(ok, msg, **extra):
        out.update(ok=ok, message=msg, finished=_now(), **extra)
        _audit_line({"event": "rollback", "ok": ok, "message": msg, "target_id": request_id, **extra})
        return out

    if target not in ("dev", "prod"):
        return done(False, f"invalid target '{target}'")

    try:
        with _Lock(LOCK_PATH, "rollback"):
            mf_path = _select_manifest(request_id)
            if not mf_path:
                if request_id:
                    return done(False, f"no rollback record found for request '{request_id}'")
                return done(False, "nothing to roll back — no processed request recorded")
            mf = json.loads(mf_path.read_text())
            rtype = mf.get("type"); rid = mf.get("request_id")
            data_rel = mf.get("data_file"); data_snap = mf.get("data_snapshot")
            page_snaps = mf.get("page_snapshots", {})   # rel -> snapshot path (vacancy/awards)
            deployed = mf.get("deployed_paths", [])
            added_keys = mf.get("added_keys", [])
            import deployer as dep_mod
            site_root = REPO_ROOT / dep_mod.SITE_ROOT_REL

            # 1) RESTORE local state
            if data_rel and (REPO_ROOT / data_rel).is_file():
                # data-driven: SURGICALLY remove this request's record(s), then rebuild.
                # (Surgical, not snapshot-restore, so newer same-type requests survive.)
                if added_keys:
                    _remove_records_by_key(data_rel, added_keys)
                elif data_snap and Path(data_snap).is_file():
                    shutil.copy2(data_snap, REPO_ROOT / data_rel)  # fallback: snapshot restore
                build_script = TYPE_SPECS.get(rtype, {}).get("build")
                if build_script:
                    bp = _run(["python3", str(REPO_ROOT / build_script)], cwd=REPO_ROOT)
                    if bp.returncode != 0:
                        return done(False, f"rollback: rebuild failed (rc={bp.returncode})")
            elif page_snaps:
                # HTML-direct (vacancy/awards): restore the edited pages from snapshot
                for rel, snap_path in page_snaps.items():
                    if Path(snap_path).is_file():
                        shutil.copy2(snap_path, site_root / rel)
            else:
                return done(False, f"cannot roll back {rid}: no snapshot recorded")

            # 2) RE-DEPLOY per deployed path. Two cases:
            #    - PERMANENT pages (listings, career, awards, docs — the type's fixed _TYPE_PAGES):
            #      re-upload the restored version so dev matches the rolled-back state.
            #    - TRANSIENT pages (a news ARTICLE page, i.e. not in _TYPE_PAGES): the record was
            #      removed, so this page must NOT exist anymore → delete it from BOTH disk and
            #      storage. (build-news.py leaves the orphaned article file on disk, so we can't
            #      rely on "not local.is_file()" — must check membership in the permanent set.)
            account = dep_mod.DEV_ACCOUNT if target == "dev" else dep_mod.PROD_ACCOUNT
            permanent = {p.lstrip("/") for p in _TYPE_PAGES.get(rtype, [])}
            deleted, reuploaded, failed = 0, 0, []
            for blob in deployed:
                local = site_root / blob
                if blob in permanent:
                    if local.is_file():
                        ok, _ = dep_mod._az_upload(account, local, blob)  # restored → overwrite
                        reuploaded += 1 if ok else 0
                        if not ok:
                            failed.append(blob)
                else:
                    # transient (news article): delete from disk + storage
                    try:
                        local.unlink(missing_ok=True)
                    except OSError:
                        pass
                    cp = subprocess.run(
                        ["az", "storage", "blob", "delete", "--account-name", account,
                         "--auth-mode", "login", "--container-name", "$web", "--name", blob,
                         "--only-show-errors"],
                        capture_output=True, text=True, timeout=60)
                    deleted += 1 if cp.returncode == 0 else 0
                    if cp.returncode != 0:
                        failed.append(blob)

            # 3) archive the manifest so a second rollback doesn't re-undo
            mf_path.rename(mf_path.with_suffix(".done"))

            msg = (f"rolled back {rtype} request '{rid}' on {target}: restored state, "
                   f"deleted {deleted} + re-uploaded {reuploaded} page(s)")
            if failed:
                msg += f" ({len(failed)} storage op(s) failed)"
            return done(True, msg, undid=rid)
    except OperatorError as e:
        return done(False, str(e))
    except subprocess.TimeoutExpired:
        return done(False, "rollback timed out")


def _audit_line(obj: dict) -> None:
    """Append an arbitrary JSON event to the audit log (used by the bot for auth events)."""
    try:
        obj = {"at": _now(), **obj}
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _audit(result: OperatorResult) -> None:
    """One JSON line per run — the deterministic audit trail the plan requires."""
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": result.finished_at or _now(),
                "request_id": result.request_id,
                "type": result.request_type,
                "target": result.target,
                "ok": result.ok,
                "message": result.message,
                "stages": [{"stage": s.stage, "status": s.status, "rc": s.exit_code}
                           for s in result.stages],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let audit-logging failure break a deploy


# --------------------------------------------------------------------------- #
# CLI (for local/VM testing without the bot)
# --------------------------------------------------------------------------- #

def _cli(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run the website-support operator pipeline on one request folder.")
    ap.add_argument("folder", help="path to the request folder")
    ap.add_argument("--request-id", default=None, help="id for logging (default: folder name)")
    ap.add_argument("--target", choices=["dev", "prod"], default="dev")
    ap.add_argument("--preview", action="store_true", help="dry-run only, do not apply/build")
    ap.add_argument("--deploy", action="store_true",
                    help="publish to blob storage + verify (needs `az login --identity` + RBAC)")
    args = ap.parse_args(argv)

    rid = args.request_id or Path(args.folder).resolve().name
    res = process(rid, args.folder, target=args.target, apply=not args.preview, deploy=args.deploy)
    print(res.to_json())
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
