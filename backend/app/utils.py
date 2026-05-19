# app/utils.py
from email.utils import parseaddr
from typing import Tuple

def parse_sender(from_header: str) -> Tuple[str, str]:
    name, email = parseaddr(from_header or "")
    return (name.strip(), email.strip().lower())

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def _domain(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[1].strip().lower()

def is_probably_bulk(from_email: str, from_name: str, subject: str) -> bool:
    """
    Bulk detection WITHOUT false positives on gmail.com.
    Now includes known brand marketing domains.
    """

    email = (from_email or "").lower()
    name = (from_name or "").lower()
    subj = (subject or "").lower()

    dom = _domain(email)

    # ---------------------------------------
    # 1️⃣ Known brand marketing domains
    # ---------------------------------------
    KNOWN_BULK_DOMAINS = {
        "official.nike.com",
        "nike.com",
        "l.boscovs.com",
        "em.extendedstayamerica.com",
        "emails.hertz.com",
        "linkedin.com",
        "jobleads.com",
    }

    if dom in KNOWN_BULK_DOMAINS:
        return True

    # ---------------------------------------
    # 2️⃣ Common bulk indicators
    # ---------------------------------------
    bulk_anywhere = [
        "no-reply", "noreply", "do-not-reply", "mailer-daemon",
        "newsletter", "digest", "marketing", "campaign", "promotions",
        "list-", "bounce", "bulk",

        # marketing-ish sender names / CTAs
        "offers", "deal", "deals", "discount", "sale", "promo",

        # job alerts
        "jobleads", "jobright", "indeed", "ziprecruiter", "glassdoor",
        "job alert", "jobs matching", "saved search", "apply now", "early applicant",
    ]

    blob = f"{email} {name} {subj}"
    if any(k in blob for k in bulk_anywhere):
        return True

    # ---------------------------------------
    # 3️⃣ Domain prefix patterns
    # ---------------------------------------
    bulk_domain_prefixes = (
        "mail.", "mails.", "mailer.",
        "em.", "email.", "emails.",
        "news.", "newsletter.",
        "offers.", "promo.", "promos."
    )
    if any(dom.startswith(p) for p in bulk_domain_prefixes):
        return True

    # tracking subdomains
    if dom.startswith("l.") or dom.startswith("links.") or dom.startswith("click."):
        return True

    return False