from __future__ import annotations

from typing import Any, Dict, List

from app.llm_clients import chat_json


_CRITIC_SYSTEM = """
You are a strict evaluator for email replies.
Choose the candidate that sounds most like a real human reply for the given email.
Prefer natural, grounded, brief, emotionally fitting replies.
Penalize robotic wording, over-explaining, generic assistant tone, and invented details.
Return JSON only.
""".strip()


_CRITIC_SCHEMA = """
{
  "best_candidate_id": "c1",
  "scores": {
    "c1": {"human": 0.0, "fit": 0.0, "clarity": 0.0, "safety": 0.0},
    "c2": {"human": 0.0, "fit": 0.0, "clarity": 0.0, "safety": 0.0},
    "c3": {"human": 0.0, "fit": 0.0, "clarity": 0.0, "safety": 0.0}
  },
  "reason": "string"
}
""".strip()


def choose_best_candidate(
    ctx: Dict[str, Any],
    interp: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    valid = [c for c in candidates if str(c.get("reply") or "").strip()]
    if not valid:
        return {"best_candidate_id": "", "reason": "no_valid_candidates", "scores": {}}

    body = ctx.get("body") or ""
    subject = ctx.get("subject") or "(no subject)"

    blocks = []
    for c in valid:
        blocks.append(f"{c['candidate_id']}:\n{str(c.get('reply') or '').strip()}")

    user_prompt = f"""
Original email subject:
{subject}

Original email body:
{body}

Reply target:
- tone: {interp.get("tone_to_use") or "casual"}
- length: {interp.get("length") or "short"}
- reassure: {bool(interp.get("should_reassure", False))}
- answer_directly: {bool(interp.get("should_answer_directly", True))}

Candidates:
{chr(10).join(blocks)}

Pick the best candidate.
""".strip()

    parsed = chat_json(_CRITIC_SYSTEM, user_prompt, _CRITIC_SCHEMA) or {}

    best_id = str(parsed.get("best_candidate_id") or "").strip()
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    reason = str(parsed.get("reason") or "").strip()

    if best_id not in {c["candidate_id"] for c in valid}:
        # fallback heuristic
        def _score(c: Dict[str, Any]) -> float:
            text = str(c.get("reply") or "").strip()
            if not text:
                return -1.0
            s = 0.0
            words = text.split()
            if 3 <= len(words) <= 28:
                s += 1.0
            if len(text) < 220:
                s += 0.6
            low = text.lower()
            bad_markers = [
                "i understand your concern",
                "here is a reply",
                "as an ai",
                "certainly",
                "please let me know if",
                "thank you for your email",
            ]
            if not any(m in low for m in bad_markers):
                s += 1.0
            if body and "?" in body and "?" in text:
                s += 0.2
            return s

        best = sorted(valid, key=_score, reverse=True)[0]
        best_id = best["candidate_id"]

    return {
        "best_candidate_id": best_id,
        "scores": scores,
        "reason": reason,
    }