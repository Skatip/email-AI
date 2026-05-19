import re
from dataclasses import dataclass
from typing import List
from app.llm_clients import chat_json

@dataclass
class IntentResult:
    intent: str
    confidence: float
    signals: List[str]

_MEETING = re.compile(
    r"\b("
    r"zoom|teams|google meet|meet\.google\.com|calendar invite|"
    r"join( the)? (call|meeting)|dial[ -]?in|"
    r"scheduled|reschedule|invite(?:d)? to (a )?meeting|"
    r"meeting (today|tomorrow)|"
    r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b"
    r")\b",
    re.I
)

# Make security stricter (avoid false positives)
_SECURITY = re.compile(
    r"\b("
    r"security alert|suspicious|unusual activity|new sign-?in|"
    r"password reset|verify your identity|2-step|2fa|otp code|"
    r"account locked|reset your password|login attempt"
    r")\b",
    re.I
)

_TIME = re.compile(r"\b(today|tonight|asap|immediately|urgent|deadline|in\s+\d+\s+minutes|by\s+\d{1,2}(:\d{2})?\s*(am|pm)?)\b", re.I)
_MONEY = re.compile(r"\b(invoice|payment|paid|refund|charge|billing|balance|overdue)\b", re.I)

# Job/newsletter patterns (treat as promotion/bulk unless user marks VIP)
_JOBS = re.compile(
    r"\b("
    r"new jobs|job alert|jobs matching|saved search|recommended jobs|"
    r"apply now|early applicant|jobleads|jobright|indeed|ziprecruiter|"
    r"linkedin jobs|glassdoor"
    r")\b",
    re.I
)

_PROMO = re.compile(
    r"\b("
    r"unsubscribe|manage preferences|view online|email preferences|"
    r"sale|offer|% off|promo code|deal|limited time|shop now|clearance|"
    r"free gift|gift with purchase|final days|ends today|last chance|"
    r"save \$|save up to|new arrivals|exclusive|rsvp|prom shop|"
    r"newsletter|digest|recommended for you"
    r")\b",
    re.I
)

def extract_intent(subject: str, body: str, thread_context: str = "") -> IntentResult:
    text = f"SUBJECT:\n{subject}\n\nBODY:\n{body}\n\nTHREAD_CONTEXT:\n{thread_context}".strip()
    if not text:
        return IntentResult(intent="empty", confidence=0.2, signals=["no_text"])

    # FAST PATH FIRST
    if _SECURITY.search(text):
        conf = 0.80 + (0.10 if _TIME.search(text) else 0.0)
        return IntentResult(intent="security", confidence=min(0.95, conf), signals=["security_terms"])

    if _MEETING.search(text):
        conf = 0.65 + (0.15 if _TIME.search(text) else 0.0)
        return IntentResult(intent="meeting", confidence=min(0.92, conf), signals=["meeting_terms"])

    if _MONEY.search(text):
        conf = 0.60 + (0.15 if _TIME.search(text) else 0.0)
        return IntentResult(intent="money", confidence=min(0.90, conf), signals=["money_terms"])

    # Job alerts should behave like promotions by default
    if _JOBS.search(text):
        return IntentResult(intent="promotion", confidence=0.85, signals=["job_alert"])

    if _PROMO.search(text):
        return IntentResult(intent="promotion", confidence=0.80, signals=["promo_terms"])

    # LLM for ambiguous only
    system = (
        "You classify email intent for priority notifications. "
        "Be conservative: promotions/newsletters/job alerts are usually low priority. "
        "Security alerts, meetings, and direct action requests are higher."
    )
    schema = """
Return ONLY valid JSON:
{
  "intent": "security|meeting|money|action_required|promotion|general",
  "confidence": 0.0-1.0,
  "signals": ["short reasons"]
}
"""
    out = chat_json(system, text[:6000], schema)
    if out and isinstance(out, dict) and "intent" in out:
        intent = str(out.get("intent", "general")).strip()
        conf = float(out.get("confidence", 0.5) or 0.5)
        signals = out.get("signals") or []
        if not isinstance(signals, list):
            signals = [str(signals)]
        return IntentResult(
            intent=intent if intent else "general",
            confidence=max(0.0, min(1.0, conf)),
            signals=[str(s)[:80] for s in signals][:8],
        )

    return IntentResult(intent="general", confidence=0.45, signals=[])