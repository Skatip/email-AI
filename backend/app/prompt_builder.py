from __future__ import annotations

from typing import Any, Dict, List


def _style_memory_summary(examples: List[Dict[str, Any]]) -> str:
    if not examples:
        return "No examples."

    lines = []
    for i, ex in enumerate(examples[:2], 1):
        out = str(ex.get("outbox_text") or "").strip()
        if not out:
            continue
        out = " ".join(out.split())
        if len(out) > 120:
            out = out[:117] + "..."
        lines.append(f"{i}. {out}")

    return "\n".join(lines) if lines else "No examples."


def build_generation_messages(
    ctx: Dict[str, Any],
    interp: Dict[str, Any],
    rag_examples: List[Dict[str, Any]],
    variant_idx: int,
) -> List[Dict[str, str]]:
    subject = ctx.get("subject") or "(no subject)"
    body = ctx.get("body") or ""
    relationship = ctx.get("relationship") or "neutral"
    tone = interp.get("tone_to_use") or "direct"
    length = interp.get("length") or "short"

    variant_guidance = {
        0: "Reply in the most direct natural way.",
        1: "Reply naturally, with a little more warmth, but still brief.",
    }.get(variant_idx, "Reply naturally and briefly.")

    system = f"""
You are writing a reply AS THE USER.

Important:
- Reply to the sender's request directly.
- Do not explain the situation back to them.
- Do not summarize their message.
- Do not add details that are not in the email.
- Do not turn a short request into a long message.
- Sound like a real person.
- Keep it short: usually 1 sentence, max 2.
- Return only the reply text.

Context:
- relationship: {relationship}
- target tone: {tone}
- target length: {length}

{variant_guidance}
""".strip()

    user = f"""
Email subject:
{subject}

Email body:
{body}

Style examples:
{_style_memory_summary(rag_examples)}

Write one short reply now.
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]