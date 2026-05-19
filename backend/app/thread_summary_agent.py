from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.llm_clients import chat_json


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:1800]


def _fallback(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = len(emails or [])
    subjects = [str(e.get("subject") or "").strip() for e in emails if e.get("subject")]
    subject = subjects[0] if subjects else "this thread"

    timeline = []
    for e in emails[:8]:
        timeline.append(
            {
                "from": e.get("from", ""),
                "subject": e.get("subject", ""),
                "event": _clean(e.get("snippet") or e.get("body") or "")[:180],
                "ts": e.get("ts", 0),
            }
        )

    return {
        "summary": f"This thread contains {count} email(s) about {subject}.",
        "action_items": [],
        "decisions": [],
        "timeline": timeline,
        "participants": list(dict.fromkeys([str(e.get("from") or "") for e in emails if e.get("from")]))[:10],
        "status": "fallback",
    }


def _listify(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def summarize_thread(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    emails = emails or []
    if not emails:
        return {
            "summary": "No thread messages were found.",
            "action_items": [],
            "decisions": [],
            "timeline": [],
            "participants": [],
            "status": "empty",
        }

    combined_parts = []
    for i, e in enumerate(emails, start=1):
        combined_parts.append(
            f"""
MESSAGE {i}
FROM: {e.get('from', '')}
SUBJECT: {e.get('subject', '')}
TIME: {e.get('ts', '')}
BODY:
{_clean(e.get('body', '') or e.get('snippet', ''))}
""".strip()
        )

    combined = "\n\n---\n\n".join(combined_parts)[:9000]

    schema = """
{
  "summary": "clear short paragraph of the full thread",
  "action_items": ["specific next action, owner if known, deadline if known"],
  "decisions": ["decision or agreement from the thread"],
  "timeline": [
    {"from": "sender", "event": "what happened", "ts": "timestamp if known"}
  ],
  "participants": ["names or emails"],
  "status": "needs_action | waiting | informational | resolved"
}
""".strip()

    result = chat_json(
        system=(
            "You summarize email threads for an AI email assistant. "
            "Return only valid JSON. Be specific, structured, and useful. "
            "Do not invent facts. If no action item exists, return an empty list."
        ),
        user_prompt=combined,
        schema_hint=schema,
    )

    if not isinstance(result, dict):
        return _fallback(emails)

    return {
        "summary": str(result.get("summary") or "").strip() or _fallback(emails)["summary"],
        "action_items": [str(x).strip() for x in _listify(result.get("action_items")) if str(x).strip()],
        "decisions": [str(x).strip() for x in _listify(result.get("decisions")) if str(x).strip()],
        "timeline": _listify(result.get("timeline")) or _fallback(emails)["timeline"],
        "participants": [str(x).strip() for x in _listify(result.get("participants")) if str(x).strip()],
        "status": str(result.get("status") or "informational").strip(),
    }
