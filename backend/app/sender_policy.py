from dataclasses import dataclass
from app.db import get_sender
from app.utils import is_probably_bulk

@dataclass
class SenderPolicyResult:
    sender_band: str  # VIP | TRUSTED | PLATFORM | BULK | UNKNOWN | BLOCKED
    sender_boost: float
    reason: str

PLATFORM_DOMAINS = ("linkedin.com", "accounts.google.com", "google.com")

PERSONAL_EMAIL_DOMAINS = (
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
)

def _domain(email: str) -> str:
    s = (email or "").lower()
    if "@" not in s:
        return ""
    return s.split("@", 1)[1].strip()

def sender_policy(sender_email: str, sender_name: str, subject: str) -> SenderPolicyResult:
    s = (sender_email or "").lower().strip()
    row = get_sender(s)

    # User overrides
    if row and int(row.get("blocked", 0)) == 1:
        return SenderPolicyResult("BLOCKED", -0.40, "user_blocked")

    if row and int(row.get("vip", 0)) == 1:
        return SenderPolicyResult("VIP", 0.35, "user_vip")

    # Learned trusted
    if row and int(row.get("total_count", 0)) >= 5:
        avg = float(row.get("avg_priority", 0.0))
        high = int(row.get("high_count", 0))
        if high >= 3 and avg >= 0.70:
            return SenderPolicyResult("TRUSTED", 0.18, "learned_trusted_sender")

    # Platform senders
    if any(d in s for d in PLATFORM_DOMAINS):
        return SenderPolicyResult("PLATFORM", -0.05, "platform_sender")

    # Bulk senders
    if is_probably_bulk(sender_email, sender_name, subject):
        return SenderPolicyResult("BULK", -0.20, "bulk_sender_heuristic")

    # NEW: if it's a personal email domain + has a real name, treat as trusted by default
    dom = _domain(s)
    if dom in PERSONAL_EMAIL_DOMAINS and (sender_name or "").strip():
        return SenderPolicyResult("TRUSTED", 0.18, "personal_domain_trusted_default")

    return SenderPolicyResult("UNKNOWN", 0.0, "no_sender_history")