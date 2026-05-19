from dataclasses import dataclass
from typing import Dict, Any
import re

from app.config import settings
from app.intent_extractor import extract_intent
from app.risk_engine import compute_risk
from app.sender_policy import sender_policy
from app.coherence_engine import coherence_score
from app.utils import clamp01, parse_sender

from app.human_signals import extract_human_signals


@dataclass
class PriorityOutput:
    priority: float
    label: str
    reason: str
    intent: str
    sender_band: str
    risk: float
    coherence: float
    coherence_band: str
    respond_recommended: bool
    urgency_minutes: int
    human_signals: Dict[str, Any]


INTENT_BASE = {
    "security": 0.78,
    "meeting": 0.62,
    "money": 0.55,
    "action_required": 0.68,
    "promotion": 0.10,
    "general": 0.30,
    "empty": 0.20,
}

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "zoho.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
}

_AUTOMATED_LOCAL_RE = re.compile(
    r"(no[-_.]?reply|donotreply|do[-_.]?not[-_.]?reply|notifications?|notification|updates?|"
    r"billing|support|help|team|info|news|newsletter|alerts?|security|accounts?|noreply)",
    re.I,
)


def _label(p: float) -> str:
    if p >= settings.THRESH_HIGH:
        return "HIGH"
    if p >= settings.THRESH_MED:
        return "MEDIUM"
    return "LOW"


def _urgency_minutes(label: str, hs: Dict[str, Any]) -> int:
    if hs.get("action_intent") and hs.get("temporal_constraint"):
        return 10
    if hs.get("temporal_constraint"):
        return 30
    if label == "HIGH":
        return 30
    if label == "MEDIUM":
        return 120
    return 1440


def _infer_sender_type(sender_email: str, sender_band: str) -> str:
    email = (sender_email or "").strip().lower()
    band = (sender_band or "").upper()

    if not email or "@" not in email:
        return "UNKNOWN"

    local, domain = email.split("@", 1)

    if band in ("BULK", "PLATFORM"):
        return "AUTOMATED"

    if _AUTOMATED_LOCAL_RE.search(local):
        return "AUTOMATED"

    if domain in PERSONAL_EMAIL_DOMAINS:
        return "PERSONAL"

    return "COMPANY"


def priority_score(email: Dict[str, Any]) -> PriorityOutput:
    sender = email.get("from", "") or ""
    subject = email.get("subject", "") or ""
    body = email.get("body", "") or ""
    snippet = email.get("snippet", "") or ""
    thread_context = email.get("thread_context", "") or ""

    body_plus = f"{body}\n\nSNIPPET:\n{snippet}".strip()

    intent_res = extract_intent(subject, body_plus, thread_context)
    intent = intent_res.intent if intent_res.intent in INTENT_BASE else "general"
    base = INTENT_BASE[intent]

    risk_res = compute_risk(subject, body_plus, sender)
    risk = float(risk_res.risk_score)

    sender_name, sender_email = parse_sender(sender)
    sp = sender_policy(sender_email, sender_name, subject)
    sender_type = _infer_sender_type(sender_email, sp.sender_band)

    coh_text = f"{subject}\n{body}".strip()
    coh = coherence_score(coh_text)

    hs_obj = extract_human_signals(
        subject=subject,
        body=body_plus,
        thread_context=thread_context,
        sender_email=sender_email,
        sender_name=sender_name,
    )
    hs = hs_obj.to_dict()
    hs["sender_type"] = sender_type
    hs["risk_signals"] = risk_res.signals
    hs["risk_reasons"] = risk_res.reasons
    hs["risk_urls"] = risk_res.urls

    promo_penalty = 0.25 if intent == "promotion" else 0.0
    security_boost = 0.15 if intent == "security" else 0.0

    p = base
    p += sp.sender_boost
    p += security_boost
    p += (0.10 * risk if intent in ("security", "money") else 0.02 * risk)
    p -= promo_penalty

    rel_w = float(hs.get("relationship_weight", 0.45))

    if sp.sender_band in ("VIP", "TRUSTED"):
        p += 0.10 * rel_w

    if hs.get("action_intent"):
        p += 0.12 * float(hs.get("action_strength", 0.6))

    if hs.get("temporal_constraint"):
        p += 0.15 * float(hs.get("temporal_strength", 0.6))

    domain = hs.get("domain", "general")
    if domain == "family":
        p += 0.12
    elif domain == "health":
        p += 0.14
    elif domain in ("finance", "job"):
        p += 0.06

    if hs.get("deferred_intent"):
        p -= 0.08

    if risk >= 0.60:
        p += 0.20

    if sender_type == "COMPANY":
        if intent in ("security", "money", "action_required", "meeting"):
            p += 0.05
        elif intent == "general":
            p -= 0.06

    if sender_type == "AUTOMATED":
        if intent not in ("security", "money"):
            p -= 0.10

    if coh.band in ("LOW_COHERENCE", "GIBBERISH"):
        if sp.sender_band in ("VIP", "TRUSTED"):
            p -= 0.05
        else:
            p -= 0.20

    p = clamp01(p)

    if intent == "promotion":
        p = min(p, 0.25)

    label = _label(p)

    sender_band = (sp.sender_band or "UNKNOWN").upper()
    respond = (label in ("HIGH", "MEDIUM"))

    if not respond:
        if sender_band in ("VIP", "TRUSTED") and hs.get("action_intent") and hs.get("temporal_constraint"):
            respond = True

    if sender_band in ("BULK", "PLATFORM"):
        respond = False
        if risk >= 0.70 and intent in ("security", "money"):
            respond = True

    if sender_type == "AUTOMATED" and intent not in ("security", "money", "action_required"):
        respond = False

    if sender_type == "COMPANY" and intent == "general" and not hs.get("action_intent"):
        respond = False

    if sender_band in ("VIP", "TRUSTED") and hs.get("action_intent") and hs.get("temporal_constraint"):
        respond = True

    urgency = _urgency_minutes(label, hs)

    reason = (
        f"intent={intent} band={sp.sender_band} sender_type={sender_type} risk={risk:.2f} "
        f"coherence={coh.band} human_boost=ON hs=({','.join(hs_obj.signals[:6])})"
    )

    return PriorityOutput(
        priority=p,
        label=label,
        reason=reason,
        intent=intent,
        sender_band=sp.sender_band,
        risk=risk,
        coherence=coh.coherence,
        coherence_band=coh.band,
        respond_recommended=respond,
        urgency_minutes=urgency,
        human_signals=hs,
    )