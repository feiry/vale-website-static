"""
Operational dashboard — a lightweight who/what/when view of the bot's activity.

Reads the operator audit log (one JSON event per line: auth / process / rollback) and renders
a single self-contained HTML page: health, activity feed (with names), counts, success rate,
recent errors, and a per-user audit view. No external deps, no database — just parses the log.

Served at /dashboard on the bot's aiohttp app (behind nginx TLS). Access is gated by a token
(DASHBOARD_TOKEN) so the who-did-what trail isn't world-readable.
"""
from __future__ import annotations

import html
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG = Path(os.path.expanduser("~/ptvi-bot/repo/operator-audit.log"))
_MAX_EVENTS = 400  # how many recent lines to parse for the view


def _load_events() -> list[dict]:
    if not AUDIT_LOG.is_file():
        return []
    try:
        lines = AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-_MAX_EVENTS:]:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _fmt(ts: str) -> str:
    # ISO → "MM-DD HH:MM:SS"
    return ts.replace("T", " ")[5:19] if ts else "?"


def _name(ev: dict) -> str:
    return ev.get("sender_name") or (ev.get("sender") or "")[:8] or "?"


def render_dashboard() -> str:
    events = _load_events()
    now = datetime.now(timezone.utc)

    # split by kind
    runs = [e for e in events if "stages" in e]                      # process
    rolls = [e for e in events if e.get("event") == "rollback"]
    auths = [e for e in events if e.get("event") == "auth"]

    # counts
    ok_runs = sum(1 for r in runs if r.get("ok"))
    fail_runs = len(runs) - ok_runs
    by_type = Counter(r.get("type", "?") for r in runs)
    denials = sum(1 for a in auths if a.get("allowed") is False)
    # active users (by name) from auth events
    users = Counter(_name(a) for a in auths if a.get("allowed"))
    last_activity = max((e.get("at", "") for e in events), default="")

    # recent errors
    errors = [r for r in runs if not r.get("ok")] + [x for x in rolls if not x.get("ok")]

    # build a unified recent-activity feed (newest first)
    feed = []
    for e in events:
        at = e.get("at", "")
        if "stages" in e:
            feed.append((at, "PROCESS", e.get("type", "?"),
                         ("✅" if e.get("ok") else "❌"), e.get("request_id", ""), ""))
        elif e.get("event") == "rollback":
            feed.append((at, "ROLLBACK", "", ("✅" if e.get("ok") else "❌"),
                         e.get("target_id") or "", e.get("message", "")[:50]))
        elif e.get("event") == "auth":
            feed.append((at, "MESSAGE", "", ("🔓" if e.get("allowed") else "🚫"),
                         _name(e), e.get("utterance", "")))
    feed.sort(key=lambda x: x[0], reverse=True)

    def esc(s):
        return html.escape(str(s))

    rows = "".join(
        f"<tr><td>{esc(_fmt(at))}</td><td><span class=k>{esc(kind)}</span></td>"
        f"<td>{esc(typ)}</td><td>{icon}</td><td>{esc(who)}</td><td class=msg>{esc(msg)}</td></tr>"
        for at, kind, typ, icon, who, msg in feed[:120]
    )
    type_rows = "".join(f"<li>{esc(t)}: <b>{n}</b></li>" for t, n in by_type.most_common())
    user_rows = "".join(f"<li>{esc(u)}: <b>{n}</b> msgs</li>" for u, n in users.most_common())
    err_rows = "".join(
        f"<li>{esc(_fmt(e.get('at','')))} — {esc(e.get('type') or 'rollback')}: "
        f"{esc(e.get('message',''))[:80]}</li>"
        for e in sorted(errors, key=lambda x: x.get("at", ""), reverse=True)[:10]
    ) or "<li>none 🎉</li>"

    sr = f"{(ok_runs/len(runs)*100):.0f}%" if runs else "—"

    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>PTVI Website Bot — Dashboard</title>
<style>
 body{{font-family:system-ui,Segoe UI,Arial;margin:0;background:#0d1117;color:#e6edf3}}
 header{{background:#161b22;padding:16px 24px;border-bottom:1px solid #30363d}}
 h1{{margin:0;font-size:18px}} .sub{{color:#8b949e;font-size:13px;margin-top:4px}}
 .cards{{display:flex;flex-wrap:wrap;gap:16px;padding:24px}}
 .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;min-width:150px}}
 .card .n{{font-size:28px;font-weight:700}} .card .l{{color:#8b949e;font-size:12px;text-transform:uppercase}}
 .ok{{color:#3fb950}} .bad{{color:#f85149}}
 .grid{{display:flex;flex-wrap:wrap;gap:16px;padding:0 24px 24px}}
 .box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;flex:1;min-width:260px}}
 .box h3{{margin:0 0 8px;font-size:14px}} ul{{margin:0;padding-left:18px;font-size:13px;line-height:1.7}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #21262d}}
 th{{color:#8b949e;font-weight:600}} .k{{background:#21262d;padding:1px 6px;border-radius:4px;font-size:11px}}
 .msg{{color:#8b949e;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
</style></head><body>
<header><h1>🤖 PTVI Website Support — Operations</h1>
<div class=sub>last activity: {esc(_fmt(last_activity))} · refreshed {esc(now.strftime('%H:%M:%S'))} UTC · auto-refresh 30s</div></header>
<div class=cards>
 <div class=card><div class="n ok">{ok_runs}</div><div class=l>Published</div></div>
 <div class=card><div class="n{' bad' if fail_runs else ''}">{fail_runs}</div><div class=l>Failed</div></div>
 <div class=card><div class=n>{sr}</div><div class=l>Success rate</div></div>
 <div class=card><div class="n{' bad' if denials else ''}">{denials}</div><div class=l>Auth denials</div></div>
 <div class=card><div class=n>{len(users)}</div><div class=l>Active users</div></div>
</div>
<div class=grid>
 <div class=box><h3>By type</h3><ul>{type_rows or '<li>none</li>'}</ul></div>
 <div class=box><h3>Who's using it</h3><ul>{user_rows or '<li>none</li>'}</ul></div>
 <div class=box><h3>Recent errors</h3><ul>{err_rows}</ul></div>
</div>
<div class=grid><div class=box style="flex:1">
 <h3>Activity feed</h3>
 <table><tr><th>time</th><th>action</th><th>type</th><th></th><th>who / id</th><th>detail</th></tr>
 {rows}</table>
</div></div>
<script>setTimeout(()=>location.reload(),30000)</script>
</body></html>"""
