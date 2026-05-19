import base64
import os
import time
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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
    return {h.get("name", "").lower(): h.get("value", "") for h in (payload.get("headers", []) or [])}


def _get_plain_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []

    def walk(p: Dict[str, Any]):
        if not p:
            return
        mime = p.get("mimeType", "")
        body = p.get("body", {}) or {}
        data = body.get("data")

        if mime == "text/plain" and data:
            try:
                parts.append(base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore"))
            except Exception:
                pass

        for child in (p.get("parts", []) or []):
            walk(child)

    walk(payload or {})
    return "\n".join(parts).strip()


def _msg_to_metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
    payload = msg.get("payload", {}) or {}
    headers = _headers(payload)
    return {
        "id": msg.get("id"),
        "threadId": msg.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "snippet": msg.get("snippet", "") or "",
        "body": "",
        "thread_context": "",
        "ts": int(msg.get("internalDate", "0") or 0) // 1000,
        "labelIds": msg.get("labelIds", []) or [],
    }


def fetch_inbox_fast(query: str = "", max_results: int = 10, scan_limit: int = 80) -> List[Dict[str, Any]]:
    """
    FAST inbox: only metadata/snippet. No body, no thread, no AI.
    This is the endpoint the UI should use first.
    """
    svc = gmail_service()
    resp = svc.users().messages().list(userId="me", q=query or "", maxResults=max(scan_limit, max_results)).execute()
    msgs = resp.get("messages", []) or []

    results: List[Dict[str, Any]] = []
    for m in msgs:
        msg = svc.users().messages().get(
            userId="me",
            id=m["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        results.append(_msg_to_metadata(msg))
        if len(results) >= max_results:
            break

    return results


def fetch_email_body(message_id: str) -> Dict[str, Any]:
    svc = gmail_service()
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = msg.get("payload", {}) or {}
    headers = _headers(payload)
    return {
        "id": msg.get("id"),
        "threadId": msg.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "snippet": msg.get("snippet", "") or "",
        "body": _get_plain_text(payload),
        "ts": int(msg.get("internalDate", "0") or 0) // 1000,
        "labelIds": msg.get("labelIds", []) or [],
    }


def fetch_emails(query: str = "", max_results: int = 20, include_thread_context: bool = True, fast: bool = False) -> List[Dict[str, Any]]:
    if fast:
        return fetch_inbox_fast(query=query, max_results=max_results, scan_limit=max(max_results, 80))

    svc = gmail_service()
    resp = svc.users().messages().list(userId="me", q=query or "", maxResults=max_results).execute()
    msgs = resp.get("messages", []) or []

    results: List[Dict[str, Any]] = []
    for m in msgs:
        full = fetch_email_body(m["id"])
        thread_text = ""
        thread_id = full.get("threadId")

        if include_thread_context and thread_id:
            try:
                th = svc.users().threads().get(userId="me", id=thread_id, format="metadata").execute()
                ctx_chunks = []
                for tm in (th.get("messages", []) or [])[-2:]:
                    th_headers = _headers(tm.get("payload", {}) or {})
                    ctx_chunks.append(
                        f"FROM: {th_headers.get('from','')}\nSUBJECT: {th_headers.get('subject','')}\nSNIPPET: {tm.get('snippet','')}\n"
                    )
                thread_text = "\n---\n".join(ctx_chunks).strip()
            except Exception:
                thread_text = ""

        full["thread_context"] = thread_text
        results.append(full)

    return results


def fetch_new_emails(after_unix_ts: int, max_results: int = 20) -> List[Dict[str, Any]]:
    after_q = time.strftime("%Y/%m/%d", time.gmtime(after_unix_ts))
    emails = fetch_emails(query=f"after:{after_q}", max_results=max_results, include_thread_context=True)
    return [e for e in emails if int(e.get("ts", 0)) > int(after_unix_ts)]


def fetch_full_thread(thread_id: str):
    svc = gmail_service()
    th = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = th.get("messages", []) or []
    results = []

    for msg in messages:
        payload = msg.get("payload", {}) or {}
        headers = _headers(payload)
        results.append({
            "id": msg.get("id"),
            "threadId": thread_id,
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "body": _get_plain_text(payload),
            "snippet": msg.get("snippet", ""),
            "ts": int(msg.get("internalDate", "0") or 0) // 1000,
            "labelIds": msg.get("labelIds", []) or [],
        })

    results.sort(key=lambda x: x.get("ts", 0))
    return results
