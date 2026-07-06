from __future__ import annotations

import re
from typing import Any, Dict, List

from app.llm_clients import chat_json


def _clean(text: str, limit: int = 2200) -> str:
    text = (text or "").strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:limit]


def _listify(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _participants(emails: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for e in emails:
        sender = str(e.get("from") or "").strip()
        if not sender:
            continue
        key = sender.lower()
        if key not in seen:
            seen.add(key)
            out.append(sender)
    return out[:12]


def _attachment_lines(email: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for att in email.get("attachments") or []:
        name = att.get("filename") or "attachment"
        ftype = att.get("file_type") or att.get("document_label") or att.get("mime_type") or "file"
        lines.append(f"{name} ({ftype})")
    return lines[:8]


def _fallback(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = len(emails or [])
    subjects = [str(e.get("subject") or "").strip() for e in emails if e.get("subject")]
    subject = subjects[-1] if subjects else "this thread"
    timeline = []
    attachments: List[str] = []
    for e in emails[:10]:
        timeline.append({
            "from": e.get("from", ""),
            "subject": e.get("subject", ""),
            "event": _clean(e.get("snippet") or e.get("body") or "", 220),
            "ts": e.get("ts", 0),
        })
        attachments.extend(_attachment_lines(e))
    return {
        "summary": f"This thread contains {count} email(s) about {subject}.",
        "latest_context": _clean((emails[-1].get("body") or emails[-1].get("snippet") or "") if emails else "", 300),
        "pending_questions": [],
        "action_items": [],
        "decisions": [],
        "timeline": timeline,
        "participants": _participants(emails),
        "documents_shared": list(dict.fromkeys(attachments))[:10],
        "reply_recommendation": "Review the latest message before replying.",
        "reply_context": "Use the latest message and thread history to respond naturally.",
        "status": "informational",
        "confidence": 0.45,
    }


def summarize_thread(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    emails = emails or []
    if not emails:
        return {
            "summary": "No thread messages were found.",
            "latest_context": "",
            "pending_questions": [],
            "action_items": [],
            "decisions": [],
            "timeline": [],
            "participants": [],
            "documents_shared": [],
            "reply_recommendation": "No reply needed because no messages were found.",
            "reply_context": "",
            "status": "empty",
            "confidence": 0.0,
        }

    combined_parts = []
    for i, e in enumerate(emails[-12:], start=1):
        att = ", ".join(_attachment_lines(e))
        combined_parts.append(
            f"""
MESSAGE {i}
FROM: {e.get('from', '')}
SUBJECT: {e.get('subject', '')}
TIME: {e.get('ts', '')}
ATTACHMENTS: {att}
BODY:
{_clean(e.get('body', '') or e.get('snippet', ''))}
""".strip()
        )
    combined = "\n\n---\n\n".join(combined_parts)[:10000]

    schema = """
{
  "summary": "short human summary of the whole thread",
  "latest_context": "what the latest message is saying or asking",
  "pending_questions": ["specific unanswered question if any"],
  "action_items": ["specific next action, owner if known, deadline if known"],
  "decisions": ["decision or agreement from the thread"],
  "timeline": [{"from": "sender", "event": "what happened", "ts": "timestamp if known"}],
  "participants": ["names or emails"],
  "documents_shared": ["attachment/document names or types mentioned"],
  "reply_recommendation": "reply needed | no reply needed | optional reply | follow up later, with reason",
  "reply_context": "concise context the reply agent should use",
  "status": "needs_action | waiting | informational | resolved | follow_up_needed",
  "confidence": 0.85
}
""".strip()

    result = chat_json(
        system=(
            "You are a thread intelligence agent for an AI email assistant. "
            "Understand participants, latest context, pending questions, action items, decisions, documents, and reply need. "
            "Do not invent facts. Return only valid JSON. "
            "If the thread is just a forwarded human conversation, treat it as a human thread, not an automated system email."
        ),
        user_prompt=combined,
        schema_hint=schema,
    )
    fallback = _fallback(emails)
    if not isinstance(result, dict):
        return fallback

    def str_list(key: str, limit: int = 10) -> List[str]:
        return [str(x).strip() for x in _listify(result.get(key)) if str(x).strip()][:limit]

    timeline = result.get("timeline") if isinstance(result.get("timeline"), list) else fallback["timeline"]
    try:
        confidence = float(result.get("confidence", 0.65))
    except Exception:
        confidence = 0.65
    return {
        "summary": str(result.get("summary") or fallback["summary"]).strip(),
        "latest_context": str(result.get("latest_context") or fallback["latest_context"]).strip(),
        "pending_questions": str_list("pending_questions"),
        "action_items": str_list("action_items"),
        "decisions": str_list("decisions"),
        "timeline": timeline[:12],
        "participants": str_list("participants") or fallback["participants"],
        "documents_shared": str_list("documents_shared") or fallback["documents_shared"],
        "reply_recommendation": str(result.get("reply_recommendation") or fallback["reply_recommendation"]).strip(),
        "reply_context": str(result.get("reply_context") or fallback["reply_context"]).strip(),
        "status": str(result.get("status") or fallback["status"]).strip(),
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }
