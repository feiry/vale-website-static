"""
PTVI website-support bot — aiohttp listener + Teams activity handler.

Flow (see design doc §Flow):
  message ──▶ Layer-2 auth (auth.is_authorised) ──▶ parse_intent ──▶ operator ──▶ Adaptive Card

The bot never deploys by itself: it calls the deterministic operator (operator_svc.process) and
reports the structured result. Prod deploy requires an explicit Approve (card button / message)
AND passes the SAME auth gate as processing.
"""
from __future__ import annotations

import sys
from pathlib import Path

from aiohttp import web
from aiohttp.web import Request, Response
from botbuilder.core import TurnContext
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity, Attachment

# operator lives in the sibling operator/ package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "operator"))
import operator_svc as op  # noqa: E402

from config import Config          # noqa: E402
import auth                        # noqa: E402
import cards                       # noqa: E402
import requests_source as rs       # noqa: E402
from agent import parse_intent     # noqa: E402


DEV_BASE = "https://stptviwebbot.z23.web.core.windows.net"  # PoC dev preview (PTGDI storage; swap to Vale stidstaticsite002 when grant lands)
PROD_BASE = "https://www.valeindonesia.com"


def _preview_links(result: "op.OperatorResult") -> list[str]:
    """
    Preview URLs for the pages this run deployed — works for ALL request types.
    Primary source: result._deployed_paths (the exact pages the operator published, set for
    news/vacancy/awards/documents). Falls back to parsing the intake's EN:/ID: output lines.
    """
    seen, links = set(), []
    for rel in getattr(result, "_deployed_paths", []) or []:
        url = DEV_BASE + "/" + rel.lstrip("/")
        if url not in seen:
            seen.add(url); links.append(url)
    if not links:  # fallback: news-style EN:/ID: output
        for st in result.stages:
            for line in (st.stdout_tail or "").splitlines():
                line = line.strip()
                if line.startswith(("EN:", "ID:")) and "/" in line:
                    url = DEV_BASE + line.split(":", 1)[1].strip()
                    if url not in seen:
                        seen.add(url); links.append(url)
    return links[:6]


async def _reply_card(turn: TurnContext, card: dict):
    await turn.send_activity(Activity(
        type="message",
        attachments=[Attachment(content_type=card["contentType"], content=card["content"])],
    ))


async def on_message(turn: TurnContext):
    act = turn.activity
    sender_oid = None
    if act.from_property and act.from_property.aad_object_id:
        sender_oid = act.from_property.aad_object_id

    # --- Layer 2: verify sender on EVERY message, before any action ---
    allowed, reason = auth.is_authorised(sender_oid)
    op._audit_line({"event": "auth", "sender": sender_oid, "allowed": allowed, "reason": reason})
    if not allowed:
        await turn.send_activity("You're not authorized to submit website requests.")
        return

    intent = parse_intent(act.text or "", act.value)

    if intent.kind == "help":
        await _reply_card(turn, cards.text_card("Website support bot", [
            "• **what's pending?** — list submitted requests",
            "• **process the request** — build & deploy to dev preview (when only one is pending)",
            "• **process `<request-id>`** — process a specific request, e.g. `process sp-demo-news`",
            "• **rollback** — undo the last processed request",
            "• **rollback `<request-id>`** — undo a specific request, e.g. `rollback sp-demo-news`",
            "• **approve** — after reviewing dev, deploy to production",
        ]))
        return

    if intent.kind == "rollback":
        rid = intent.request_id  # None → last processed (LIFO); set → that specific request
        await turn.send_activity(
            f"Rolling back {rid if rid else 'the last processed request'} …")
        res = op.rollback(target="dev", request_id=rid)
        icon = "↩️" if res.get("ok") else "❌"
        await _reply_card(turn, cards.text_card(
            f"{icon} Rollback", [res.get("message", "(no result)")]))
        return

    if intent.kind == "status":
        pending = rs.list_submitted()
        await _reply_card(turn, cards.pending_card(pending))
        return

    if intent.kind in ("process", "approve_prod"):
        target = "prod" if intent.kind == "approve_prod" else "dev"
        # Prod deploy is not wired in this test build (awaiting Vale storage grant). Rather than
        # run a confusing no-op "prod" pass, tell the tester clearly and stop.
        if target == "prod":
            await turn.send_activity(
                "Prod publishing isn't enabled in this test build yet — the dev preview is the "
                "end of the flow for now. (Production deploy activates once the Vale storage "
                "access is granted.)")
            return
        rid, folder = rs.resolve(intent.request_id)
        if not folder:
            pending = rs.list_submitted()
            hint = ("no submitted requests found" if not pending else
                    "name which request: " + ", ".join(pending))
            await turn.send_activity(f"Couldn't pick a request — {hint}.")
            return

        await turn.send_activity(
            f"{'Deploying to prod' if target=='prod' else 'Processing'}: {rid} …")
        # PoC: actually deploy to dev (PTGDI storage). Prod deploy stays gated until the
        # Vale storage grant lands, so only enable real deploy for the dev target here.
        result = op.process(rid, str(folder), target=target, deploy=(target == "dev"))

        stages = [{"stage": s.stage, "status": s.status, "rc": s.exit_code} for s in result.stages]
        if target == "prod" and result.ok:
            await _reply_card(turn, cards.live_card(rid, [PROD_BASE]))
        else:
            await _reply_card(turn, cards.result_card(
                rid, result.request_type, result.ok, result.message,
                _preview_links(result), stages))
        return

    # unknown
    await turn.send_activity(
        "I didn't catch that. Try “process the request”, “what's pending?”, or “help”.")


# --- adapter + web app ---
ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(Config))


async def messages(req: Request) -> Response:
    return await ADAPTER.process(req, _BOT)


class _Bot:
    async def on_turn(self, turn: TurnContext):
        if turn.activity.type == "message":
            await on_message(turn)


_BOT = _Bot()


def create_app() -> web.Application:
    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/healthz", lambda r: web.Response(text="ok"))
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=Config.HOST, port=Config.PORT)
