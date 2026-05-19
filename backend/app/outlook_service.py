import email
import imaplib
import re
from email.header import decode_header
from typing import Any, Dict, List


def _decode(value: str) -> str:
    if not value:
        return ""
    out = ""
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            out += part.decode(enc or "utf-8", errors="ignore")
        else:
            out += str(part)
    return out.strip()


def _clean_preview(text: str, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def fetch_outlook_emails(email_user: str, app_password: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Fast Outlook inbox fetch: headers + small body preview only."""
    results: List[Dict[str, Any]] = []
    host = "outlook.office365.com"
    max_results = max(1, min(int(max_results or 10), 50))

    try:
        mail = imaplib.IMAP4_SSL(host, 993)
        mail.login(email_user, app_password)
        mail.select("inbox", readonly=True)

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            mail.logout()
            return []

        mail_ids = messages[0].split()
        latest_ids = mail_ids[-max_results:][::-1]

        for m_id in latest_ids:
            res, msg_data = mail.fetch(
                m_id,
                "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)] BODY.PEEK[TEXT]<0.1200>)",
            )
            if res != "OK":
                continue

            header_bytes = b""
            preview_bytes = b""
            for part in msg_data:
                if not isinstance(part, tuple):
                    continue
                meta = str(part[0])
                if "HEADER" in meta:
                    header_bytes += part[1]
                else:
                    preview_bytes += part[1]

            msg = email.message_from_bytes(header_bytes)
            subject = _decode(msg.get("Subject", ""))
            from_value = _decode(msg.get("From", ""))
            message_id = msg.get("Message-ID", "") or m_id.decode()

            try:
                dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                ts = int(dt.timestamp())
            except Exception:
                ts = 0

            preview = _clean_preview(preview_bytes.decode("utf-8", errors="ignore"))

            results.append({
                "id": m_id.decode(),
                "threadId": message_id,
                "from": from_value,
                "subject": subject or "",
                "snippet": preview,
                "body": "",
                "thread_context": "",
                "ts": ts,
            })

        mail.logout()
    except Exception as e:
        print(f"Backend Connection Error: {e}")
        return []

    return results
