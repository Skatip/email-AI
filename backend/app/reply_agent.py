from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

import requests

from app.rag_store import RAG_DB_PATH, embed_text, retrieve_examples

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "gpt-oss:120b-cloud").strip()

ENABLE_REFINE = False


# ============================================================
# OLLAMA
# ============================================================

def _ollama_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.76,
    num_predict: int = 120,
    timeout: int = 90,
) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": GEN_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": float(temperature),
                    "top_p": 0.92,
                    "num_predict": int(num_predict),
                    "stop": [
                        "User:",
                        "Assistant:",
                        "Reasoning:",
                        "Note:",
                        "Explanation:",
                        "Reply:",
                        "Output:",
                    ],
                },
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return ((data.get("message") or {}).get("content") or "").strip()
    except Exception as e:
        print("OLLAMA ERROR:", str(e))
        return ""


# ============================================================
# RAG SAVE
# ============================================================

def save_rag_example(inbound: str, outbound: str, label: str = "style") -> Dict[str, Any]:
    try:
        inbound = (inbound or "").strip()
        outbound = (outbound or "").strip()
        label = (label or "style").strip() or "style"

        if not inbound or not outbound:
            return {"ok": False, "error": "inbound and outbound required"}

        emb = embed_text(inbound)
        meta = {"label": label, "source": "manual_save"}

        conn = sqlite3.connect(RAG_DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reply_examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inbox_text TEXT NOT NULL,
                    outbox_text TEXT NOT NULL,
                    meta_json TEXT,
                    inbox_embed_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO reply_examples (inbox_text, outbox_text, meta_json, inbox_embed_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    inbound,
                    outbound,
                    json.dumps(meta, ensure_ascii=False),
                    json.dumps(emb or []),
                ),
            )
            conn.commit()
            return {"ok": True, "stored": True}
        finally:
            conn.close()
    except Exception as e:
        return {"ok": False, "stored": False, "error": str(e)}


# ============================================================
# CLEAN
# ============================================================

def _clean_body(text: str) -> str:
    text = (text or "").strip()

    text = re.split(
        r"(?im)^\s*(from:|sent:|subject:|to:|cc:|on .* wrote:|begin forwarded message:)\s*",
        text,
        maxsplit=1,
    )[0]

    text = re.sub(
        r"(?is)(\n|^)\s*(best regards|regards|thanks and regards|kind regards|sincerely|thank you|thanks)[\s\S]*$",
        "",
        text,
    )
    text = re.sub(r"\bcell\s*-\s*\+?\d[\d \-]{6,}\b", "", text, flags=re.I)
    text = re.sub(r"\bphone\s*-\s*\+?\d[\d \-]{6,}\b", "", text, flags=re.I)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# ============================================================
# SAFE ANALYSIS ACCESS
# ============================================================

def _safe_get_analysis_value(
    analysis: Optional[Dict[str, Any]],
    *keys: str,
    default: str = "",
) -> str:
    if not analysis:
        return default

    for key in keys:
        value = analysis.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            s = str(value).strip()
            if s:
                return s

    return default


def _infer_mode(analysis: Optional[Dict[str, Any]], body: str) -> str:
    sender_band = _safe_get_analysis_value(analysis, "sender_band", "band", default="unknown").lower()
    emotion = _safe_get_analysis_value(analysis, "emotion", "sentiment", default="neutral").lower()
    domain = _safe_get_analysis_value(analysis, "domain", default="").lower()
    intent = _safe_get_analysis_value(analysis, "intent", default="").lower()
    body_l = (body or "").lower()

    personal_markers = [
        "call me", "i need to talk", "what happened", "come home", "missed your call",
        "worried", "asap", "why didn't", "why didnt", "please call", "need to talk"
    ]
    work_markers = [
        "offer letter", "attached", "details", "document", "review", "onboarding",
        "kindly provide", "please provide", "project", "meeting"
    ]

    personal_score = 0
    work_score = 0

    if sender_band in {"vip", "trusted"}:
        personal_score += 1
    if any(x in emotion for x in ["worried", "concern", "sad", "upset", "anxious", "fear"]):
        personal_score += 2
    if domain in {"family", "personal", "relationship"}:
        personal_score += 2
    if intent in {"emotional", "personal"}:
        personal_score += 1
    if any(x in body_l for x in personal_markers):
        personal_score += 2

    if sender_band in {"platform", "bulk"}:
        work_score += 1
    if domain in {"work", "career", "hr", "finance"}:
        work_score += 2
    if intent in {"request", "information", "professional"}:
        work_score += 1
    if any(x in body_l for x in work_markers):
        work_score += 2

    return "personal" if personal_score > work_score else "work"


def _tone_from_analysis(analysis: Optional[Dict[str, Any]], body: str) -> str:
    mode = _infer_mode(analysis, body)
    emotion = _safe_get_analysis_value(analysis, "emotion", "sentiment", default="neutral").lower()
    body_l = (body or "").lower()

    if mode == "personal":
        if any(x in emotion for x in ["worried", "concern", "sad", "upset", "anxious", "fear"]):
            return "warm_immediate"
        return "casual_immediate"

    if any(x in body_l for x in ["offer letter", "kindly provide", "attached", "review", "details"]):
        return "professional_clean"

    return "natural"




def _analysis_lower(analysis: Optional[Dict[str, Any]], key: str, default: str = "") -> str:
    return str((analysis or {}).get(key, default) or default).strip().lower()


def _analysis_value_any(analysis: Optional[Dict[str, Any]], *keys: str, default: str = "") -> str:
    if not analysis:
        return default
    for key in keys:
        value = analysis.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    hs = analysis.get("human_signals") or {}
    if isinstance(hs, dict):
        for key in keys:
            value = hs.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    basic = analysis.get("basic_classification") or {}
    if isinstance(basic, dict):
        for key in keys:
            value = basic.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return default


def _rule_based_human_reply(body: str, analysis: Optional[Dict[str, Any]]) -> str:
    """
    Very small safety layer before Ollama.
    It prevents hallucinated facts like inventing calendar availability.
    This is intentionally narrow and only handles common direct questions.
    """
    text = (body or "").strip()
    low = text.lower()

    asks_availability = (
        "available" in low
        and any(x in low for x in ["today", "tomorrow", "this week", "now", "later"])
    )
    asks_call = any(x in low for x in ["call", "talk", "discuss"])

    if asks_availability and asks_call:
        return "Yes, I should be available today. What time were you thinking?"

    if asks_availability:
        return "Yes, I should be available today. What time works for you?"

    if "let me know" in low and asks_call:
        return "Sure, let me know what time works for you."

    return ""


def _should_suppress_reply(email: Dict[Any, Any], analysis: Optional[Dict[str, Any]], body: str, force: bool = False) -> tuple[bool, str]:
    """
    Human behavior rule: do not draft replies for notifications, promotions,
    bills, security alerts, spam, or automated system messages unless the user
    explicitly forces generation.
    """
    if force:
        return False, ""

    sender = str(email.get("from") or "").lower()
    subject = str(email.get("subject") or "").lower()
    text = f"{subject}\n{body}".lower()

    sender_band = _analysis_lower(analysis, "sender_band", "")
    intent = _analysis_lower(analysis, "intent", "")
    category = (
        _analysis_value_any(analysis, "email_type", "email_category", "category", default="")
        .replace("_", " ")
        .lower()
    )
    relation = (
        _analysis_value_any(analysis, "relationship_type", "relationship", default="")
        .replace("_", " ")
        .lower()
    )
    sender_type = _analysis_value_any(analysis, "sender_type", default="").lower()
    source_folder = _analysis_value_any(analysis, "source_folder", default="").lower()

    hs = (analysis or {}).get("human_signals") or {}
    if isinstance(hs, dict):
        sender_type = sender_type or str(hs.get("sender_type") or "").lower()

    risk = float((analysis or {}).get("risk") or 0.0)
    respond_recommended = (analysis or {}).get("respond_recommended", None)

    hard_no_reply = [
        "paperless", "statement", "document is ready", "security zone", "sign in security",
        "verification code", "confirmation", "receipt", "password reset", "alert", "notification",
        "unsubscribe", "view online", "do not reply", "donotreply", "no-reply", "noreply",
        "newsletter", "promotion", "offer", "rewards", "deal", "discount",
    ]

    no_reply_classes = {"promotional", "promotion", "promo", "bill", "billing", "security", "automated", "notification", "transactional"}
    no_reply_intents = {"security", "bill", "billing", "promotion", "promotional", "notification", "transactional_system", "general"}
    no_reply_senders = {"bulk", "platform", "automated"}

    # Spam-folder email can still be useful if it is clearly conversational/work/personal.
    spam_but_human = (
        source_folder == "spam"
        and category in {"conversational", "work", "company work", "family personal"}
        and relation in {"family personal", "family", "personal", "company work", "work", "company"}
    )

    if respond_recommended is False and not spam_but_human:
        return True, "No reply needed for this email."
    if source_folder == "spam" and category == "spam" and not spam_but_human:
        return True, "No reply generated for spam email."
    if sender_band in no_reply_senders and not spam_but_human:
        return True, f"No reply needed for {sender_band} sender."
    if sender_type in {"automated", "bulk", "platform", "company"} and any(x in text or x in sender for x in hard_no_reply):
        return True, "No reply needed for automated notification."
    if category in no_reply_classes:
        return True, f"No reply needed for {category} email."
    if intent in no_reply_intents and any(x in text or x in sender for x in hard_no_reply):
        return True, f"No reply needed for {intent} email."
    if risk >= 0.70 and relation not in {"family personal", "family", "personal", "company work", "work", "company"}:
        return True, "No reply generated for high-risk or suspicious email."

    return False, ""


# ============================================================
# STYLE EXAMPLES
# ============================================================

def _style_examples(body: str, analysis: Optional[Dict[str, Any]]) -> List[str]:
    try:
        query = "\n".join(
            x for x in [
                body,
                _safe_get_analysis_value(analysis, "intent", default=""),
                _safe_get_analysis_value(analysis, "emotion", "sentiment", default=""),
                _safe_get_analysis_value(analysis, "domain", default=""),
            ] if x
        ).strip()

        if not query:
            return []

        rows = retrieve_examples(query, k=5, max_scan=3000, min_score=0.28)

        out: List[str] = []
        seen = set()

        for row in rows:
            txt = str(row.get("outbox_text") or "").strip()
            if not txt:
                continue

            txt = " ".join(txt.split())
            key = txt.lower()
            if key in seen:
                continue
            seen.add(key)

            out.append(txt)
            if len(out) >= 2:
                break

        return out
    except Exception as e:
        print("STYLE EXAMPLE ERROR:", str(e))
        return []


def _style_block(examples: List[str]) -> str:
    if not examples:
        return ""

    joined = "\n".join(f"- {x}" for x in examples)
    return (
        "Here are a few examples of the user's usual reply style. "
        "Use them lightly as style reference only, and do not copy wording.\n\n"
        f"{joined}"
    )


# ============================================================
# CONTEXT
# ============================================================

def _build_context_block(analysis: Optional[Dict[str, Any]], body: str) -> str:
    mode = _infer_mode(analysis, body)
    tone = _tone_from_analysis(analysis, body)
    intent = _safe_get_analysis_value(analysis, "intent", default="")
    emotion = _safe_get_analysis_value(analysis, "emotion", "sentiment", default="")
    domain = _safe_get_analysis_value(analysis, "domain", default="")
    urgency = _safe_get_analysis_value(analysis, "urgency", "temporal", default="")

    parts = [
        f"conversation_mode={mode}",
        f"tone_mode={tone}",
    ]
    if intent:
        parts.append(f"intent={intent}")
    if emotion:
        parts.append(f"emotion={emotion}")
    if domain:
        parts.append(f"domain={domain}")
    if urgency:
        parts.append(f"urgency={urgency}")

    return "Context:\n" + "\n".join(parts)


# ============================================================
# PROMPTS
# ============================================================

def _build_generation_messages(
    body: str,
    analysis: Optional[Dict[str, Any]],
    style_examples: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    style_examples = style_examples or []
    style_block = _style_block(style_examples)
    context_block = _build_context_block(analysis, body)
    mode = _infer_mode(analysis, body)

    mode_guidance = (
        "If this is personal, reply like an active real conversation: immediate, human, and not distant."
        if mode == "personal"
        else "If this is work-related, stay clean, natural, and simple without sounding stiff."
    )

    system_instruction = f"""
You are writing a reply to a real human message as the user.

First behave like a human: if the email is an automated alert, bill notice, security notification, newsletter, promotion, receipt, or document-ready message, the correct response is no reply.

For real conversational emails only, write the kind of reply a real person would naturally send in that exact situation.

Keep it short, natural, and context-aware.
Usually 1 or 2 sentences.
Match the emotional tone of the message naturally.
It is okay to sound casual when the message is casual.
It is okay to reply with immediacy when the message feels immediate.
{mode_guidance}

Do not over-explain.
Do not sound robotic, scripted, corporate, or overly polished.
Do not output labels, headings, markdown, or explanations.

Never invent facts, times, availability, meeting slots, promises, attachments, or completed actions.
If the sender asks whether the user is available and no calendar availability is provided, ask what time works instead of inventing a time.
If the message is unclear or missing information, ask a brief natural clarification question.

Return only the reply text.
""".strip()

    user_parts = [body, context_block]
    if style_block:
        user_parts.append(style_block)

    user_prompt = "\n\n".join(x for x in user_parts if x).strip()

    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]


def _build_retry_messages(body: str, analysis: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    mode = _infer_mode(analysis, body)

    if mode == "personal":
        system_instruction = """
Reply like a real person texting back in an active conversation.

Be natural, immediate, and conversational.
Do not sound formal, distant, scheduled, or like customer support.
Keep it short.
Return only the reply.
""".strip()
    else:
        system_instruction = """
Write a short natural reply as a real person.

Be clear, simple, and human.
Do not sound robotic or overly polished.
Keep it short.
Return only the reply.
""".strip()

    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": body},
    ]


def _build_refine_messages(body: str, candidate_reply: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": """
Make this reply slightly smoother if needed.

Keep it short and natural.
Do not make it more formal.
Do not make it more polite.
Do not add extra wording.
Do not add new facts.
Return only the final reply text.
""".strip(),
        },
        {
            "role": "user",
            "content": f"Original message:\n{body}\n\nDraft reply:\n{candidate_reply}",
        },
    ]


# ============================================================
# POSTPROCESS / QUALITY
# ============================================================

def _postprocess(reply: str) -> str:
    reply = (reply or "").strip()
    if not reply:
        return ""

    reply = reply.strip('"').strip("'")
    reply = re.sub(r"^```[\w-]*\s*", "", reply).strip()
    reply = re.sub(r"\s*```$", "", reply).strip()
    reply = re.sub(r"^(reply|response|assistant|draft|output)\s*:\s*", "", reply, flags=re.I).strip()
    reply = reply.replace(" ,", ",")
    reply = re.sub(r"\s+", " ", reply).strip()

    lower = reply.lower()
    if any(lower.startswith(x) for x in ("here is", "here's", "the reply", "final reply", "a natural reply")):
        return ""

    if lower in {"no reply", "n/a", "none", "null", "empty"}:
        return ""

    parts = re.split(r"(?<=[.!?])\s+", reply)
    if len(parts) > 2:
        reply = " ".join(parts[:2]).strip()

    return reply


def _is_incomplete_reply(reply: str) -> bool:
    reply = (reply or "").strip()
    if not reply:
        return True

    lower = reply.lower()

    if lower in {"sorry", "sure", "okay", "ok", "what time", "let me know when"}:
        return True

    if len(reply.split()) <= 2 and not re.search(r"[.!?]$", reply):
        return True

    if reply.endswith(("—", "-", ":", ",")):
        return True

    return False


# ============================================================
# RESPONSE HELPERS
# ============================================================

def _empty_result(
    email: Dict[Any, Any],
    tone: str,
    force: bool,
    analysis: Optional[Dict[str, Any]],
    error: str,
    used_rag: bool = False,
) -> Dict[str, Any]:
    return {
        "sender": (email.get("from") or "").strip(),
        "reply": "",
        "tone": tone,
        "confidence": 0.0,
        "reply_meta": {
            "strategy": "pure_dynamic_style_mirroring",
            "model": GEN_MODEL,
            "force": bool(force),
            "used_rag": used_rag,
            "suppressed": False,
            "regenerated": False,
            "refined": False,
            "reply_intent": _safe_get_analysis_value(analysis, "intent", default=""),
            "error": error,
        },
        "meta": {
            "strategy": "pure_dynamic_style_mirroring",
            "model": GEN_MODEL,
            "force": bool(force),
            "reply_meta": {
                "used_rag": used_rag,
                "refined": False,
                "error": error,
            },
        },
    }


# ============================================================
# MAIN
# ============================================================

def draft_reply(
    email: Dict[Any, Any],
    analysis: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    raw_body = email.get("body") or email.get("snippet") or ""
    body = _clean_body(raw_body)
    tone = _tone_from_analysis(analysis, body)

    if not body:
        return _empty_result(email, tone, bool(force), analysis, "empty_email_body", used_rag=False)

    suppress, suppress_reason = _should_suppress_reply(email, analysis, body, force=bool(force))
    if suppress:
        result = _empty_result(email, tone, bool(force), analysis, suppress_reason, used_rag=False)
        result["safety_blocked"] = True
        result["safety_reason"] = suppress_reason
        result["reply_meta"]["suppressed"] = True
        result["reply_meta"]["suppress_reason"] = suppress_reason
        result["meta"]["reply_meta"]["suppressed"] = True
        result["meta"]["reply_meta"]["suppress_reason"] = suppress_reason
        return result

    safe_reply = _rule_based_human_reply(body, analysis)
    if safe_reply:
        return {
            "sender": (email.get("from") or "").strip(),
            "reply": safe_reply,
            "tone": tone,
            "confidence": 0.91,
            "reply_meta": {
                "strategy": "safe_reply_goal_no_hallucination",
                "model": "rule_guard_before_ollama",
                "force": bool(force),
                "used_rag": False,
                "suppressed": False,
                "regenerated": False,
                "refined": False,
                "reply_intent": "ask_clarification",
            },
            "meta": {
                "strategy": "safe_reply_goal_no_hallucination",
                "model": "rule_guard_before_ollama",
                "force": bool(force),
                "reply_meta": {
                    "used_rag": False,
                    "refined": False,
                    "regenerated": False,
                },
            },
        }

    style_examples = _style_examples(body, analysis)
    used_rag = bool(style_examples)

    gen_messages = _build_generation_messages(body, analysis, style_examples)
    raw_reply = _ollama_chat(
        messages=gen_messages,
        temperature=0.76,
        num_predict=120,
        timeout=90,
    )
    reply = _postprocess(raw_reply)

    regenerated = False
    retry_reply = ""

    if not reply or _is_incomplete_reply(reply):
        retry_messages = _build_retry_messages(body, analysis)
        retry_reply = _ollama_chat(
            messages=retry_messages,
            temperature=0.80,
            num_predict=100,
            timeout=90,
        )
        retry_candidate = _postprocess(retry_reply)
        regenerated = True

        if retry_candidate and not _is_incomplete_reply(retry_candidate):
            reply = retry_candidate
        elif not reply:
            reply = retry_candidate

    if not reply or _is_incomplete_reply(reply):
        return _empty_result(email, tone, bool(force), analysis, "provider_unavailable", used_rag=used_rag)

    refined = False
    if ENABLE_REFINE:
        refine_messages = _build_refine_messages(body, reply)
        raw_refined_reply = _ollama_chat(
            messages=refine_messages,
            temperature=0.22,
            num_predict=60,
            timeout=90,
        )
        refined_reply = _postprocess(raw_refined_reply)

        if refined_reply and not _is_incomplete_reply(refined_reply):
            if len(refined_reply) >= len(reply) * 0.65:
                reply = refined_reply
                refined = True

    confidence = 0.84
    if refined:
        confidence += 0.02
    if used_rag:
        confidence += 0.02
    if regenerated:
        confidence -= 0.01
    confidence = max(0.0, min(confidence, 0.92))

    return {
        "sender": (email.get("from") or "").strip(),
        "reply": reply,
        "tone": tone,
        "confidence": confidence,
        "reply_meta": {
            "strategy": "pure_dynamic_style_mirroring",
            "model": GEN_MODEL,
            "force": bool(force),
            "used_rag": used_rag,
            "suppressed": False,
            "regenerated": regenerated,
            "refined": refined,
            "reply_intent": _safe_get_analysis_value(analysis, "intent", default=""),
        },
        "meta": {
            "strategy": "pure_dynamic_style_mirroring",
            "model": GEN_MODEL,
            "force": bool(force),
            "reply_meta": {
                "used_rag": used_rag,
                "refined": refined,
                "regenerated": regenerated,
            },
        },
    }