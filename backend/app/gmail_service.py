import base64
import os
import re
import time
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import settings
from app.attachment_analysis import classify_attachment, attachment_risk

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# User requirement: show Gmail messages from Primary and Spam only, within 1 week.
# We intentionally do NOT use -unsubscribe or broad sender blocking because that was hiding real emails.
DAYS_BACK = 7
PRIMARY_QUERY = f"in:inbox category:primary newer_than:{DAYS_BACK}d"
PRIMARY_FALLBACK_QUERY = f"in:inbox newer_than:{DAYS_BACK}d"
SPAM_QUERY = f"in:spam newer_than:{DAYS_BACK}d"

NOISE_CATEGORY_LABELS = {
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_FORUMS",
}

# Updates often contains bills, HR, school, and interview messages, so do not block it here.
# We classify it later as BILL / WORK / PROMOTIONAL instead of hiding it.
PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "live.com", "msn.com", "proton.me", "protonmail.com",
}

BILL_WORDS = [
    "bill", "billing", "invoice", "payment", "paid", "due", "statement", "receipt",
    "balance", "amount", "autopay", "subscription", "charge", "charged", "past due",
]

WORK_WORDS = [
    "interview", "meeting", "schedule", "calendar", "project", "deadline", "manager",
    "hr", "recruiter", "job", "offer", "position", "application", "resume", "client",
    "team", "work", "office", "professor", "university", "course", "assignment",
]

FAMILY_WORDS = [
    "wife", "husband", "mom", "mother", "dad", "father", "brother", "sister",
    "family", "home", "come home", "call me", "pick up", "kids", "child",
]

PROMO_WORDS = [
    "unsubscribe", "manage preferences", "sale", "discount", "coupon", "offer",
    "promotion", "promotional", "deal", "limited time", "shop now", "newsletter",
    "marketing", "save", "% off", "clearance",
]

CONVERSATION_WORDS = [
    "please", "can you", "could you", "would you", "let me know", "wanted to",
    "need to", "call", "talk", "discuss", "question", "available", "thanks",
]


def _ensure_dir_for_file(file_path: str) -> None:
    d = os.path.dirname(file_path)
    if d:
        os.makedirs(d, exist_ok=True)


def gmail_service():
    creds = None
    cred_path = settings.GMAIL_CREDENTIALS_PATH
    token_path = settings.GMAIL_TOKEN_PATH

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Missing Gmail OAuth credentials.json at: {cred_path}")

    _ensure_dir_for_file(token_path)

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _headers(payload: Dict[str, Any]) -> Dict[str, str]:
    return {
        h.get("name", "").lower(): h.get("value", "")
        for h in (payload.get("headers", []) or [])
    }


def _decode_body(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


def _get_plain_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []

    def walk(p: Dict[str, Any]):
        if not p:
            return

        mime = p.get("mimeType", "")
        body = p.get("body", {}) or {}
        data = body.get("data")

        if mime == "text/plain" and data:
            parts.append(_decode_body(data))

        for child in (p.get("parts", []) or []):
            walk(child)

    walk(payload or {})
    return "\n".join(parts).strip()


def _extract_email(sender: str) -> str:
    sender = sender or ""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).strip().lower()
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", sender, flags=re.I)
    return match.group(0).lower() if match else sender.lower()


def _domain(sender: str) -> str:
    email = _extract_email(sender)
    return email.split("@")[-1].lower() if "@" in email else ""


def _contains_any(text: str, words: List[str]) -> bool:
    text = (text or "").lower()
    return any(w in text for w in words)


def _is_primary_like(label_ids: List[str]) -> bool:
    labels = set(label_ids or [])
    if "SPAM" in labels:
        return True
    if "INBOX" not in labels:
        return False
    if labels.intersection(NOISE_CATEGORY_LABELS):
        return False
    return True


def classify_email(email: Dict[str, Any]) -> Dict[str, Any]:
    labels = set(email.get("labelIds") or [])
    sender = email.get("from", "") or ""
    subject = email.get("subject", "") or ""
    snippet = email.get("snippet", "") or ""
    body = email.get("body", "") or ""
    text = f"{subject}\n{snippet}\n{body[:2000]}".lower()
    domain = _domain(sender)

    source_folder = "spam" if "SPAM" in labels else "primary"

    has_bill = _contains_any(text, BILL_WORDS)
    has_promo = _contains_any(text, PROMO_WORDS)
    has_work = _contains_any(text, WORK_WORDS)
    has_family = _contains_any(text, FAMILY_WORDS) or domain in PERSONAL_DOMAINS
    has_conversation = _contains_any(text, CONVERSATION_WORDS) or has_family or has_work

    # Important: Spam folder does not automatically mean useless.
    # If a spam-folder email looks conversational or work-related, keep it visible
    # and classify it by actual meaning. The UI can still show source_folder=SPAM.
    if has_bill:
        email_type = "BILL"
    elif has_promo and not has_conversation:
        email_type = "PROMOTIONAL"
    elif has_conversation:
        email_type = "CONVERSATIONAL"
    elif "SPAM" in labels:
        email_type = "SPAM"
    else:
        email_type = "CONVERSATIONAL"

    if has_family:
        relationship_type = "FAMILY_PERSONAL"
    elif has_work or (domain and domain not in PERSONAL_DOMAINS):
        relationship_type = "COMPANY_WORK"
    else:
        relationship_type = "UNKNOWN"

    email["source_folder"] = source_folder
    email["email_type"] = email_type
    email["relationship_type"] = relationship_type
    email["basic_classification"] = {
        "email_type": email_type,
        "relationship_type": relationship_type,
        "source_folder": source_folder,
        "domain": domain,
    }
    return email



def _extract_attachments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []

    def walk(p: Dict[str, Any]):
        if not p:
            return

        filename = p.get("filename") or ""
        body = p.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        mime_type = p.get("mimeType", "") or ""
        size = int(body.get("size", 0) or 0)

        if filename and attachment_id:
            file_type = classify_attachment(filename, mime_type)
            risk = attachment_risk(filename, mime_type)

            attachments.append({
                "filename": filename,
                "mime_type": mime_type,
                "file_type": file_type,
                "attachment_id": attachment_id,
                "size": size,
                "risk_level": risk.get("risk_level", "low"),
                "risk_score": risk.get("risk_score", 0.05),
                "risk_reasons": risk.get("risk_reasons", []),
            })

        for child in (p.get("parts", []) or []):
            walk(child)

    walk(payload or {})
    return attachments


def _msg_to_email(msg: Dict[str, Any], include_body: bool = False) -> Dict[str, Any]:
    payload = msg.get("payload", {}) or {}
    headers = _headers(payload)
    attachments = _extract_attachments(payload)

    email = {
        "id": msg.get("id"),
        "threadId": msg.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "snippet": msg.get("snippet", "") or "",
        "body": _get_plain_text(payload) if include_body else "",
        "thread_context": "",
        "ts": int(msg.get("internalDate", "0") or 0) // 1000,
        "labelIds": msg.get("labelIds", []) or [],
        "attachments": attachments,
        "has_attachments": bool(attachments),
    }
    return classify_email(email)


def _append_user_query(base_query: str, user_query: str) -> str:
    q = (user_query or "").strip()
    if not q:
        return base_query
    return f"{base_query} {q}".strip()


def _list_message_ids(query: str, max_results: int, include_spam_trash: bool = False) -> List[str]:
    svc = gmail_service()
    resp = (
        svc.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_results,
            includeSpamTrash=include_spam_trash,
        )
        .execute()
    )
    return [m["id"] for m in (resp.get("messages", []) or [])]


def _primary_and_spam_ids(user_query: str = "", scan_limit: int = 80) -> List[str]:
    # Try true Gmail Primary first.
    ids = _list_message_ids(_append_user_query(PRIMARY_QUERY, user_query), scan_limit, False)

    # Fallback: some accounts/API responses don't return category:primary reliably.
    # In fallback, fetch inbox and keep primary-like labels after metadata/body fetch.
    if not ids:
        ids = _list_message_ids(_append_user_query(PRIMARY_FALLBACK_QUERY, user_query), scan_limit, False)

    spam_ids = _list_message_ids(_append_user_query(SPAM_QUERY, user_query), scan_limit, True)

    out: List[str] = []
    seen = set()
    for mid in ids + spam_ids:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def fetch_inbox_fast(
    query: str = "",
    max_results: int = 10,
    scan_limit: int = 80,
) -> List[Dict[str, Any]]:
    svc = gmail_service()
    ids = _primary_and_spam_ids(query, max(scan_limit, max_results * 5))

    results: List[Dict[str, Any]] = []
    for message_id in ids:
        msg = (
            svc.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        email = _msg_to_email(msg, include_body=False)

        if not _is_primary_like(email.get("labelIds", [])):
            continue

        results.append(email)
        if len(results) >= max_results:
            break

    return results


def fetch_email_body(message_id: str) -> Dict[str, Any]:
    svc = gmail_service()
    msg = (
        svc.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    return _msg_to_email(msg, include_body=True)


def fetch_emails(
    query: str = "",
    max_results: int = 20,
    include_thread_context: bool = True,
    fast: bool = False,
) -> List[Dict[str, Any]]:
    if fast:
        return fetch_inbox_fast(
            query=query,
            max_results=max_results,
            scan_limit=max(max_results * 5, 80),
        )

    ids = _primary_and_spam_ids(query, max(max_results * 5, 80))
    results: List[Dict[str, Any]] = []

    for message_id in ids:
        full = fetch_email_body(message_id)

        if not _is_primary_like(full.get("labelIds", [])):
            continue

        thread_text = ""
        thread_id = full.get("threadId")

        if include_thread_context and thread_id:
            try:
                th = (
                    gmail_service()
                    .users()
                    .threads()
                    .get(userId="me", id=thread_id, format="metadata")
                    .execute()
                )

                ctx_chunks = []
                for tm in (th.get("messages", []) or [])[-4:]:
                    th_headers = _headers(tm.get("payload", {}) or {})
                    ctx_chunks.append(
                        "FROM: "
                        + th_headers.get("from", "")
                        + "\nSUBJECT: "
                        + th_headers.get("subject", "")
                        + "\nSNIPPET: "
                        + tm.get("snippet", "")
                    )

                thread_text = "\n---\n".join(ctx_chunks).strip()
            except Exception:
                thread_text = ""

        full["thread_context"] = thread_text
        results.append(classify_email(full))

        if len(results) >= max_results:
            break

    return results


def fetch_new_emails(after_unix_ts: int, max_results: int = 20) -> List[Dict[str, Any]]:
    emails = fetch_emails(
        query="",
        max_results=max_results,
        include_thread_context=True,
    )
    return [e for e in emails if int(e.get("ts", 0)) > int(after_unix_ts)]


def fetch_full_thread(thread_id: str):
    svc = gmail_service()
    th = (
        svc.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )

    results = []
    for msg in th.get("messages", []) or []:
        results.append(_msg_to_email(msg, include_body=True))

    results.sort(key=lambda x: x.get("ts", 0))
    return results



def fetch_gmail_attachment(message_id: str, attachment_id: str) -> bytes:
    svc = gmail_service()
    att = (
        svc.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = att.get("data", "")
    if not data:
        return b""
    return base64.urlsafe_b64decode(data.encode("utf-8"))
