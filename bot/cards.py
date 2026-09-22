"""
Adaptive Card builders — what the bot posts back into the Teams channel.

Two cards matter for the flow:
  - result_card(...)  : status of a dev build/deploy, with preview links + an [Approve for prod] button
  - live_card(...)    : final "it's live" confirmation with the prod URLs
The Approve button emits an Action.Submit carrying {action:"approve_prod", request_id:...}, which
comes back to the bot as a normal message activity (value payload) — the same Layer-2 auth gate
applies before prod deploy.
"""
from __future__ import annotations


def _card(body: list, actions: list | None = None) -> dict:
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}


def result_card(request_id: str, rtype: str, ok: bool, message: str,
                preview_links: list[str], stages: list[dict]) -> dict:
    status_icon = "✅" if ok else "❌"
    body = [
        {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
         "text": f"{status_icon} {rtype or 'request'} — {request_id}"},
        {"type": "TextBlock", "wrap": True, "text": message},
    ]
    if stages:
        facts = [{"title": s.get("stage", "?"), "value": f'{s.get("status","?")}'
                  + (f' (rc={s["rc"]})' if s.get("rc") is not None else "")}
                 for s in stages]
        body.append({"type": "FactSet", "facts": facts})
    if preview_links:
        body.append({"type": "TextBlock", "weight": "Bolder", "text": "Preview:"})
        for url in preview_links:
            body.append({"type": "TextBlock", "wrap": True,
                         "text": f"[{url}]({url})"})

    actions = []
    # Only offer the prod-approval button when the dev step actually succeeded.
    if ok:
        actions.append({
            "type": "Action.Submit", "title": "Approve for prod",
            "data": {"action": "approve_prod", "request_id": request_id},
            "style": "positive",
        })
    return _card(body, actions or None)


def live_card(request_id: str, urls: list[str]) -> dict:
    body = [
        {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
         "text": f"🚀 Live — {request_id}"},
        {"type": "TextBlock", "wrap": True, "text": "Deployed to production and verified:"},
    ]
    for url in urls:
        body.append({"type": "TextBlock", "wrap": True, "text": f"[{url}]({url})"})
    return _card(body)


def text_card(title: str, lines: list[str]) -> dict:
    body = [{"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": title}]
    for ln in lines:
        body.append({"type": "TextBlock", "wrap": True, "text": ln})
    return _card(body)
