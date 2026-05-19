import imaplib
import email
from email.header import decode_header
import datetime
from email.utils import parsedate_to_datetime


def _decode_mime_value(value):
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(part)
    return "".join(out).strip()


def _extract_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in content_disposition.lower():
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore").strip()
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore").strip()
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(errors="ignore").strip()
        return ""


def _extract_ts(msg):
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt is None:
            return int(datetime.datetime.now().timestamp())
        return int(dt.timestamp())
    except Exception:
        return int(datetime.datetime.now().timestamp())


def fetch_outlook_imap(user_email, app_password, folder="INBOX", limit=10):
    mail = imaplib.IMAP4_SSL("outlook.office365.com")

    try:
        mail.login(user_email, app_password)
        mail.select(folder)

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            raise Exception("Failed to search mailbox")

        email_ids = messages[0].split()
        latest_ids = email_ids[-limit:]
        results = []

        for e_id in reversed(latest_ids):
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            if res != "OK":
                continue

            for response_part in msg_data:
                if not isinstance(response_part, tuple):
                    continue

                msg = email.message_from_bytes(response_part[1])

                subject = _decode_mime_value(msg.get("Subject"))
                sender = _decode_mime_value(msg.get("From"))
                body_text = _extract_text(msg)
                snippet = body_text[:200] if body_text else "Click to view content"

                results.append({
                    "id": e_id.decode(),
                    "from": sender,
                    "subject": subject or "(no subject)",
                    "snippet": snippet,
                    "body": body_text,
                    "ts": _extract_ts(msg),
                    "provider": "outlook",
                })

        mail.logout()
        return results

    except Exception as e:
        print(f"IMAP Error: {e}")
        try:
            mail.logout()
        except Exception:
            pass
        return []