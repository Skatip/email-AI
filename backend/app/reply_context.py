from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


def parse_sender_parts(from_value: str) -> Tuple[str, str]:
    s = (from_value or "").strip()
    m = re.match(r'^(.*?)\s*<([^>]+)>$', s)
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip().lower()
    if "@" in s:
        return "", s.lower()
    return s, ""


def clean_body(text: str) -> str:
    text = (text or "").strip()

    # remove common reply quotes / forwarded sections
    text = re.split(
        r"(?im)^\s*(from:|sent:|subject:|to:|cc:|on .* wrote:|begin forwarded message:)\s*",
        text,
        maxsplit=1,
    )[0]

    # remove common signature trails
    text = re.sub(
        r"(?is)(\n|^)\s*(best regards|regards|thanks and regards|kind regards|sincerely|thank you|thanks)[\s\S]*$",
        "",
        text,
    )

    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # if still multiline, compress lightly
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _safe_value(d: Optional[Dict[str, Any]], *keys: str, default: str = "") -> str:
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            s = str(v).strip()
            if s:
                return s
    return default


def build_reply_context(
    email: Dict[str, Any],
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    analysis = analysis or {}

    subject = str(email.get("subject") or "").strip()
    raw_body = email.get("body") or email.get("snippet") or ""
    body = clean_body(raw_body)

    sender_name, sender_email = parse_sender_parts(str(email.get("from") or ""))

    human_signals = analysis.get("human_signals") or {}
    if not isinstance(human_signals, dict):
        human_signals = {}

    sender_band = _safe_value(analysis, "sender_band", "band", default="UNKNOWN").upper() or "UNKNOWN"
    intent = _safe_value(analysis, "intent", "category", default="unknown").lower()
    label = _safe_value(analysis, "label", "priority_label", default="MEDIUM").upper()
    urgency_minutes = _safe_value(analysis, "urgency_minutes", default="")
    coherence_band = _safe_value(analysis, "coherence_band", default="")
    user_pref = analysis.get("user_pref") or {}
    if not isinstance(user_pref, dict):
        user_pref = {}

    emotion = (
        _safe_value(human_signals, "emotion", default="")
        or _safe_value(analysis, "emotion", "sentiment", default="neutral")
    ).lower()

    domain = _safe_value(human_signals, "domain", default="general").lower()
    temporal_type = _safe_value(human_signals, "temporal_type", default="").lower()
    action_intent = bool(human_signals.get("action_intent", False))
    deferred_intent = bool(human_signals.get("deferred_intent", False))
    relationship_weight = float(human_signals.get("relationship_weight", 0.0) or 0.0)

    relationship = "neutral"
    if sender_band in {"VIP", "TRUSTED"} or relationship_weight >= 0.75:
        relationship = "close"
    elif sender_band in {"PLATFORM", "BULK"}:
        relationship = "transactional"
    elif sender_email.endswith(("gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com")):
        relationship = "personal"

    reply_goal = "acknowledge"
    if action_intent:
        reply_goal = "respond_to_request"
    elif "question" in intent or "?" in body:
        reply_goal = "answer_or_follow_up"
    elif emotion in {"concerned", "sad", "angry", "worried", "anxious"}:
        reply_goal = "reassure"
    elif deferred_intent:
        reply_goal = "acknowledge_deferred"

    tone_hint = "natural"
    if relationship in {"close", "personal"}:
        tone_hint = "warm"
    if sender_band in {"PLATFORM", "BULK"}:
        tone_hint = "neutral"
    if domain in {"job", "finance"}:
        tone_hint = "professional"
    if emotion in {"concerned", "sad", "worried", "anxious"}:
        tone_hint = "supportive"
    if label == "HIGH" or temporal_type in {"now", "today", "by"}:
        tone_hint = "direct"

    length_hint = "short"
    body_len = len(body.split())
    if body_len > 70:
        length_hint = "medium"
    if relationship in {"close", "personal"} and emotion in {"concerned", "sad", "worried", "anxious"}:
        length_hint = "short"

    return {
        "email_id": email.get("id"),
        "from": email.get("from") or "",
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "body": body,
        "sender_band": sender_band,
        "relationship": relationship,
        "intent": intent,
        "label": label,
        "urgency_minutes": urgency_minutes,
        "coherence_band": coherence_band,
        "emotion": emotion or "neutral",
        "domain": domain or "general",
        "temporal_type": temporal_type or "",
        "action_intent": action_intent,
        "deferred_intent": deferred_intent,
        "reply_goal": reply_goal,
        "tone_hint": tone_hint,
        "length_hint": length_hint,
        "user_pref": user_pref,
        "human_signals": human_signals,
        "analysis": analysis,
    }