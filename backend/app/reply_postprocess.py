from __future__ import annotations

from app.llm_clients import chat


_REFINER_SYSTEM = """
You lightly refine an email reply to make it sound natural and human.

Rules:
- Do not change the meaning.
- Do not add any new information.
- Do not make it longer unless needed for natural flow.
- Keep it conversational and human.
- Remove robotic or assistant-like wording if present.
- Keep it brief, usually 1 to 3 sentences.
- Return only the refined reply text.
""".strip()


_FALLBACK_SYSTEM = """
You write a very short natural human email reply.

Rules:
- Reply only based on the email text.
- Do not invent facts.
- Do not sound robotic or like an AI assistant.
- Keep it brief.
- Return only the reply text.
""".strip()


def refine_reply(reply: str) -> str:
    text = (reply or "").strip()
    if not text:
        return text

    improved = chat(
        _REFINER_SYSTEM,
        text,
        temperature=0.2,
        max_tokens=90,
    ).strip()

    return improved or text


def fallback_reply(body: str, emotion: str = "neutral", urgent: bool = False) -> str:
    prompt = f"""
Email body:
{(body or '').strip()}

Context:
- emotion: {emotion}
- urgent: {urgent}

Write one short natural reply.
""".strip()

    out = chat(
        _FALLBACK_SYSTEM,
        prompt,
        temperature=0.3,
        max_tokens=60,
    ).strip()

    return out or "Got it."