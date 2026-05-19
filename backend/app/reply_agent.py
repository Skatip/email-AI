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
You are writing a reply to a message as the user.

Write the kind of reply a real person would naturally send in that exact situation.

Keep it short, natural, and context-aware.
Usually 1 or 2 sentences.
Match the emotional tone of the message naturally.
It is okay to sound casual when the message is casual.
It is okay to reply with immediacy when the message feels immediate.
{mode_guidance}

Do not over-explain.
Do not sound robotic, scripted, corporate, or overly polished.
Do not output labels, headings, markdown, or explanations.

If the message is unclear, ask a brief natural clarification question.

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