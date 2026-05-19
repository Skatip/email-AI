from __future__ import annotations

from typing import Any, Dict

from app.llm_clients import chat_json


_INTERPRETER_SYSTEM = """
You analyze an email for reply writing.
You do NOT write the reply.
Be practical, grounded, and brief.
Infer only what is strongly supported by the message and metadata.
Return concise JSON only.
""".strip()


_INTERPRETER_SCHEMA = """
{
  "situation": "string",
  "primary_need": "string",
  "tone_to_use": "casual|warm|supportive|direct|professional|neutral",
  "length": "one_line|short|medium",
  "should_reassure": true,
  "should_answer_directly": true,
  "should_ask_followup": false,
  "must_not_do": ["string", "string"],
  "must_include": ["string", "string"]
}
""".strip()


def interpret_reply_need(ctx: Dict[str, Any]) -> Dict[str, Any]:
    body = ctx.get("body") or ""
    subject = ctx.get("subject") or ""
    sender_band = ctx.get("sender_band") or "UNKNOWN"
    relationship = ctx.get("relationship") or "neutral"
    emotion = ctx.get("emotion") or "neutral"
    domain = ctx.get("domain") or "general"
    reply_goal = ctx.get("reply_goal") or "acknowledge"
    tone_hint = ctx.get("tone_hint") or "natural"
    length_hint = ctx.get("length_hint") or "short"

    user_prompt = f"""
Email subject:
{subject or "(no subject)"}

Email body:
{body}

Reply context:
- sender_band: {sender_band}
- relationship: {relationship}
- emotion: {emotion}
- domain: {domain}
- reply_goal: {reply_goal}
- tone_hint: {tone_hint}
- length_hint: {length_hint}

Analyze what kind of reply a normal human would send.
Keep it grounded to the email. Do not invent hidden facts.
""".strip()

    parsed = chat_json(_INTERPRETER_SYSTEM, user_prompt, _INTERPRETER_SCHEMA) or {}

    tone_to_use = str(parsed.get("tone_to_use") or tone_hint or "natural").strip().lower()
    if tone_to_use == "natural":
        tone_to_use = "casual"

    length = str(parsed.get("length") or "").strip().lower()
    if length not in {"one_line", "short", "medium"}:
        length = "medium" if length_hint == "medium" else "short"

    must_not_do = parsed.get("must_not_do")
    if not isinstance(must_not_do, list):
        must_not_do = []
    must_not_do = [str(x).strip() for x in must_not_do if str(x).strip()]

    must_include = parsed.get("must_include")
    if not isinstance(must_include, list):
        must_include = []
    must_include = [str(x).strip() for x in must_include if str(x).strip()]

    return {
        "situation": str(parsed.get("situation") or "").strip(),
        "primary_need": str(parsed.get("primary_need") or reply_goal).strip(),
        "tone_to_use": tone_to_use,
        "length": length,
        "should_reassure": bool(parsed.get("should_reassure", emotion in {"concerned", "sad", "worried", "anxious"})),
        "should_answer_directly": bool(parsed.get("should_answer_directly", True)),
        "should_ask_followup": bool(parsed.get("should_ask_followup", False)),
        "must_not_do": must_not_do[:6],
        "must_include": must_include[:6],
    }