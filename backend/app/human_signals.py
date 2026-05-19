import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from app.sender_policy import sender_policy

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_NO_REPLY_RE = re.compile(r"\bno[-_ ]?reply\b", re.I)
_DO_NOT_REPLY = re.compile(r"\b(do not reply|donotreply|noreply)\b", re.I)

_FOOTER_CUES = [
    "unsubscribe", "manage preferences", "email preferences",
    "privacy policy", "terms of service",
    "do not reply", "donotreply", "this is an automated message",
    "view in browser", "you are receiving this email",
]

# Weak verbs that appear in footers
_WEAK_ACTIONS = {"reply", "respond", "email", "message", "do"}

# Marketing CTA words (should NOT count as action intent for BULK/PLATFORM)
_CTA_WORDS = {
    "shop", "checkout", "check out", "buy", "order", "save", "deal", "deals",
    "offer", "offers", "browse", "explore", "learn more", "view", "see", "discover",
    "apply", "start", "get started", "sign up", "book", "reserve",
    "review", "open", "click", "tap", "download", "claim",
}

def _strip_email_addresses(text: str) -> str:
    return _EMAIL_RE.sub(" ", text or "")

def _normalize_text_for_signals(text: str) -> str:
    t = _strip_email_addresses(text or "")
    t = _NO_REPLY_RE.sub("noreply", t)
    return t

def _strip_footer_boilerplate(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    kept = []
    for line in lines:
        low = line.lower().strip()
        if any(cue in low for cue in _FOOTER_CUES):
            continue
        kept.append(line)
    joined = "\n".join(kept)

    # Cut off typical footer blocks if present
    for cue in ["unsubscribe", "privacy policy", "terms of service", "manage preferences"]:
        idx = joined.lower().find(cue)
        if idx != -1:
            joined = joined[:idx]
            break
    return joined.strip()

def _uniq(items: List[str], limit: int = 8) -> List[str]:
    seen = set()
    out = []
    for x in items:
        xx = (x or "").strip()
        if not xx:
            continue
        key = xx.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(xx[:60])
        if len(out) >= limit:
            break
    return out

# ✅ NEW: Imperative-start detection (human request style)
# Examples:
# "Give the code ASAP"
# "Please send the link"
# "Push the changes"
_IMPERATIVE_START = re.compile(
    r"(?im)^\s*(please\s+)?(give|send|share|forward|provide|push|upload|submit|confirm|verify|approve)\b"
)

# Action verbs (broad)
# ✅ Added: give, provide, push, upload
_ACTION = re.compile(
    r"\b("
    r"call( me)?|reply|respond|text( me)?|message( me)?|email( me)?|"
    r"give|provide|send|share|forward|push|upload|"
    r"review|approve|sign|submit|confirm|verify|"
    r"schedule|reschedule|cancel|pay|complete|"
    r"apply|shop|checkout|book|reserve|grab|come"
    r")\b",
    re.I
)

# Temporal markers
_TIME = re.compile(
    r"\b(before|after|by\b|asap|urgent|immediately|right away|now|"
    r"today|tonight|tomorrow|deadline|due\b|midnight|end of day|eod)\b",
    re.I
)

# Deferred intent
_DEFER = re.compile(
    r"\b(we('?ll| will)\s+(talk|discuss)\s+later|let('?s| us)\s+(talk|discuss)\s+later|"
    r"no rush|can wait|whenever you can)\b",
    re.I
)

# Domains
_FAMILY = re.compile(r"\b(wife|husband|son|daughter|kid|child|family|home|college|admission|keys?)\b", re.I)
_FINANCE = re.compile(r"\b(invoice|payment|billing|balance|bank|credit|debit|tax|loan|refund)\b", re.I)
_HEALTH = re.compile(r"\b(doctor|hospital|emergency|pain|fever|sick|medicine|clinic)\b", re.I)
_JOB = re.compile(r"\b(work|office|meeting|deadline|manager|project|interview|hiring|offer letter|git|push)\b", re.I)

# Emotion
_CONCERN = re.compile(r"\b(concerned|worried|worry|anxious|scared|afraid)\b", re.I)
_ANGER = re.compile(r"\b(angry|upset|furious|mad|disappointed)\b", re.I)
_POSITIVE = re.compile(r"\b(thank you|thanks|great|good news|awesome|congrats)\b", re.I)

# ✅ Dependency / access / blocked-progress patterns
_NEED = re.compile(r"\b(i\s+need|need\s+the|need\s+a|need\s+my)\b", re.I)
_KEYWORDS_DEP = re.compile(r"\b(keys?|key|badge|id\s*card|pass|wallet|charger|documents?|paperwork|passport)\b", re.I)
_BLOCKED = re.compile(r"\b(can'?t|cannot|unable to|locked out|stuck|stranded|won'?t work|not working)\b", re.I)
_IMPLICIT_ASK = re.compile(r"\b(can you|could you|would you|do you have|where is|where are)\b", re.I)

@dataclass
class HumanSignals:
    action_intent: bool
    action_strength: float
    action_verbs: List[str]

    temporal_constraint: bool
    temporal_type: Optional[str]
    temporal_strength: float
    temporal_markers: List[str]

    deferred_intent: bool
    deferred_markers: List[str]

    domain: str
    domain_markers: List[str]

    emotion: str
    emotion_strength: float
    emotion_markers: List[str]

    sender_band: str
    relationship_weight: float
    relationship_reason: str

    signals: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_intent": self.action_intent,
            "action_strength": self.action_strength,
            "action_verbs": self.action_verbs,
            "temporal_constraint": self.temporal_constraint,
            "temporal_type": self.temporal_type,
            "temporal_strength": self.temporal_strength,
            "temporal_markers": self.temporal_markers,
            "deferred_intent": self.deferred_intent,
            "deferred_markers": self.deferred_markers,
            "domain": self.domain,
            "domain_markers": self.domain_markers,
            "emotion": self.emotion,
            "emotion_strength": self.emotion_strength,
            "emotion_markers": self.emotion_markers,
            "sender_band": self.sender_band,
            "relationship_weight": self.relationship_weight,
            "relationship_reason": self.relationship_reason,
            "signals": self.signals,
        }

def _relationship_weight_from_band(band: str) -> float:
    b = (band or "").upper()
    if b == "VIP":
        return 0.95
    if b == "TRUSTED":
        return 0.80
    if b == "PLATFORM":
        return 0.35
    if b == "BULK":
        return 0.15
    if b == "BLOCKED":
        return 0.0
    return 0.45

def _has_cta(text_lower: str) -> bool:
    tl = text_lower or ""
    for w in _CTA_WORDS:
        if w in tl:
            return True
    return False

def extract_human_signals(subject: str, body: str, thread_context: str, sender_email: str, sender_name: str) -> HumanSignals:
    raw = f"SUBJECT:\n{subject}\n\nBODY:\n{body}\n\nTHREAD_CONTEXT:\n{thread_context}".strip()
    text = _strip_footer_boilerplate(_normalize_text_for_signals(raw))
    low = text.lower()

    sp = sender_policy(sender_email, sender_name, subject or "")
    sender_band = sp.sender_band
    rel_w = _relationship_weight_from_band(sender_band)
    bulk_like = (sender_band or "").upper() in ("BULK", "PLATFORM")

    signals: List[str] = [f"sender_band:{sender_band}", f"relationship_weight:{rel_w:.2f}"]

    # -------------------------
    # Action intent
    # -------------------------
    hits = _ACTION.findall(text) if text else []
    action_verbs = _uniq([h[0] if isinstance(h, tuple) else str(h) for h in hits], limit=6)
    action_verbs_l = [v.lower() for v in action_verbs]

    action_strength = 0.0

    # ✅ NEW: Imperative start is strong action intent
    if _IMPERATIVE_START.search(text):
        action_strength = 0.90
        # capture the imperative verb if possible
        m = _IMPERATIVE_START.search(text)
        if m:
            v = (m.group(2) or "").strip().lower()
            if v:
                action_verbs = _uniq(action_verbs + [v], limit=6)
                action_verbs_l = [vv.lower() for vv in action_verbs]

    if re.search(r"\bcall me\b", low):
        action_strength = max(action_strength, 0.95)
    elif re.search(r"\bplease\b.*\b(call|confirm|approve|sign|submit|verify|pay|send|share|give|push|upload)\b", low):
        action_strength = max(action_strength, 0.85)
    elif action_verbs:
        action_strength = max(action_strength, 0.70)

    # hard suppression if do-not-reply style
    if _DO_NOT_REPLY.search(low):
        action_strength = 0.0
        action_verbs = []
        action_verbs_l = []

    # ✅ Implicit dependency / "I need X" logic (TRUSTED/VIP only)
    if (sender_band or "").upper() in ("TRUSTED", "VIP"):
        has_need = bool(_NEED.search(low))
        has_dep_obj = bool(_KEYWORDS_DEP.search(low))
        has_blocked = bool(_BLOCKED.search(low))
        implicit_ask = bool(_IMPLICIT_ASK.search(low))

        if (has_need and has_dep_obj) or (has_blocked and has_dep_obj) or (implicit_ask and has_dep_obj):
            action_strength = max(action_strength, 0.85)
            action_verbs = _uniq((action_verbs or []) + ["need_dependency"], limit=6)
            action_verbs_l = [v.lower() for v in action_verbs]

    # BULK/PLATFORM suppression rules:
    if bulk_like and action_verbs_l:
        only_weak = all(v in _WEAK_ACTIONS for v in action_verbs_l)
        has_direct_ask = bool(re.search(r"\b(please|can you|could you|would you)\b", low))
        has_strong = any(v in {"confirm", "approve", "sign", "submit", "verify", "pay"} for v in action_verbs_l)

        if only_weak and not has_direct_ask and not has_strong:
            action_strength = 0.0
            action_verbs = []
            action_verbs_l = []

        # CTA-only downgrade
        if _has_cta(low) and not has_direct_ask and not has_strong:
            action_strength = 0.0
            action_verbs = []
            action_verbs_l = []

    action_intent = action_strength >= 0.50
    if action_intent:
        signals.append("action_intent")
    if (sender_band or "").upper() in ("TRUSTED", "VIP") and "need_dependency" in [v.lower() for v in (action_verbs or [])]:
        signals.append("dependency_need")

    # -------------------------
    # Temporal constraint
    # -------------------------
    time_hits = _TIME.findall(text) if text else []
    temporal_markers = _uniq([h[0] if isinstance(h, tuple) else str(h) for h in time_hits], limit=6)

    temporal_type = None
    temporal_strength = 0.0
    if "before" in low:
        temporal_type, temporal_strength = "before", 0.90
    elif re.search(r"\b(by|due|deadline|midnight|eod|end of day)\b", low):
        temporal_type, temporal_strength = "by", 0.85
    elif re.search(r"\b(asap|urgent|immediately|right away|now)\b", low):
        temporal_type, temporal_strength = "now", 1.00
    elif re.search(r"\b(today|tonight)\b", low):
        temporal_type, temporal_strength = "today", 0.70
    elif re.search(r"\btomorrow\b", low):
        temporal_type, temporal_strength = "tomorrow", 0.55

    # Soft-marketing temporal downgrade for BULK/PLATFORM
    if bulk_like and temporal_type == "now":
        if not re.search(r"\b(by|due|deadline|before|midnight|eod|end of day)\b", low):
            temporal_strength = 0.25
            temporal_type = "soft_marketing"

    temporal_constraint = temporal_strength >= 0.50
    if temporal_constraint:
        signals.append(f"temporal:{temporal_type}")

    # -------------------------
    # Deferred intent
    # -------------------------
    deferred_intent = bool(_DEFER.search(text))
    deferred_markers = ["talk_later"] if deferred_intent else []
    if deferred_intent:
        signals.append("deferred_intent")

    # -------------------------
    # Domain (life impact)
    # -------------------------
    domain = "general"
    domain_markers: List[str] = []
    if _FAMILY.search(text):
        domain = "family"; domain_markers.append("family_terms")
    elif _HEALTH.search(text):
        domain = "health"; domain_markers.append("health_terms")
    elif _FINANCE.search(text):
        domain = "finance"; domain_markers.append("finance_terms")
    elif _JOB.search(text):
        domain = "job"; domain_markers.append("job_terms")

    if domain != "general":
        signals.append(f"domain:{domain}")

    # -------------------------
    # Emotion
    # -------------------------
    emotion = "neutral"
    emotion_strength = 0.0
    emotion_markers: List[str] = []

    if _CONCERN.search(text):
        emotion = "concerned"; emotion_strength = 0.60; emotion_markers.append("concern_terms")
    if _ANGER.search(text):
        emotion = "angry"; emotion_strength = 0.75; emotion_markers.append("anger_terms")
    if _POSITIVE.search(text) and emotion == "neutral":
        emotion = "positive"; emotion_strength = 0.25; emotion_markers.append("positive_terms")

    if emotion != "neutral":
        signals.append(f"emotion:{emotion}")

    return HumanSignals(
        action_intent=action_intent,
        action_strength=float(action_strength),
        action_verbs=action_verbs,

        temporal_constraint=temporal_constraint,
        temporal_type=temporal_type,
        temporal_strength=float(temporal_strength),
        temporal_markers=temporal_markers,

        deferred_intent=deferred_intent,
        deferred_markers=deferred_markers,

        domain=domain,
        domain_markers=domain_markers,

        emotion=emotion,
        emotion_strength=float(emotion_strength),
        emotion_markers=emotion_markers,

        sender_band=sender_band,
        relationship_weight=float(rel_w),
        relationship_reason=sp.reason,

        signals=signals[:16],
    )