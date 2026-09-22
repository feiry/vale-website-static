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

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


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

def process(request_id: str, folder: str | os.PathLike, target: str = "dev",
            apply: bool = True, deployer=None) -> OperatorResult:
    """
    Run the deterministic pipeline for one request folder.

    request_id : opaque id for logging/audit (e.g. the SharePoint folder name)
    folder     : path to the request folder (already fetched locally by the caller)
    target     : "dev" or "prod" — controls where the deploy step publishes
    apply      : if False, stop after a successful dry-run (preview only, no writes)
    deployer   : optional callable(target, result) -> StageResult for the deploy step.
                 If None, deploy+verify are reported as PLANNED (not yet wired to Vale storage).

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
            if deployer is None:
                result.stages.append(StageResult(
                    Stage.DEPLOY, Status.PLANNED,
                    detail=f"deploy to {target} not wired yet (awaiting Vale storage grant)"))
                result.stages.append(StageResult(
                    Stage.VERIFY, Status.PLANNED, detail="verify runs after deploy is wired"))
                return finish(True, f"{rtype} applied + built locally; deploy to {target} PLANNED (not yet wired)")

            dep = deployer(target, result)
            result.stages.append(dep)
            if dep.status != Status.OK:
                return finish(False, f"deploy to {target} failed: {dep.detail}")

            return finish(True, f"{rtype} deployed to {target} and verified")

    except OperatorError as e:
        result.stages.append(StageResult(Stage.DETECT, Status.FAILED, detail=str(e)))
        return finish(False, str(e))
    except subprocess.TimeoutExpired as e:
        result.stages.append(StageResult(Stage.BUILD, Status.FAILED, detail=f"timeout: {e}"))
        return finish(False, "a step timed out")


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
    args = ap.parse_args(argv)

    rid = args.request_id or Path(args.folder).resolve().name
    res = process(rid, args.folder, target=args.target, apply=not args.preview)
    print(res.to_json())
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
