from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from app.db import connect


def _now() -> int:
    return int(time.time())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    status = status.strip().lower()
    allowed = {"pending", "due", "done", "dismissed", "snoozed"}
    return status if status in allowed else None


def _relative_reminder_ts(note: str = "", default_seconds: int = 3600) -> int:
    low = (note or "").lower()
    if "tomorrow" in low:
        return _now() + 24 * 3600
    if "tonight" in low:
        return _now() + 6 * 3600
    if "next week" in low:
        return _now() + 7 * 24 * 3600
    m = re.search(r"in\s+(\d+)\s*(minute|minutes|min|hour|hours|hr|hrs|day|days)", low)
    if m:
        n = _safe_int(m.group(1), 1)
        unit = m.group(2)
        if unit.startswith("min"):
            return _now() + n * 60
        if unit.startswith("hour") or unit.startswith("hr"):
            return _now() + n * 3600
        if unit.startswith("day"):
            return _now() + n * 24 * 3600
    return _now() + default_seconds


def create_followup(email_id: str, remind_at: Any, note: str = "", thread_id: str = "", subject: str = "", sender: str = "", provider: str = "gmail") -> Dict[str, Any]:
    if not email_id:
        raise ValueError("email_id is required")
    remind_ts = _safe_int(remind_at)
    if remind_ts <= 0:
        remind_ts = _relative_reminder_ts(note)

    conn = connect()
    cur = conn.cursor()
    # Avoid duplicate pending reminders for same email/thread at same time window.
    existing = cur.execute(
        """
        SELECT * FROM followup_reminders
        WHERE email_id=? AND status IN ('pending','due','snoozed')
        ORDER BY remind_at ASC
        LIMIT 1
        """,
        (email_id,),
    ).fetchone()
    if existing:
        conn.close()
        return {"status": "exists", "followup": dict(existing)}

    cur.execute(
        """
        INSERT INTO followup_reminders(
            email_id, thread_id, remind_at, status, note, created_at,
            subject, sender, provider, triggered_at, completed_at
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (email_id, thread_id or "", remind_ts, "pending", note or "", _now(), subject or "", sender or "", provider or "gmail", None, None),
    )
    new_id = cur.lastrowid
    conn.commit()
    row = cur.execute("SELECT * FROM followup_reminders WHERE id=?", (new_id,)).fetchone()
    conn.close()
    return {"status": "created", "followup": dict(row)}


def list_followups(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    conn = connect()
    cur = conn.cursor()
    limit = max(1, min(_safe_int(limit, 100), 500))
    status = _normalize_status(status)
    if status:
        rows = cur.execute(
            """
            SELECT * FROM followup_reminders
            WHERE status=?
            ORDER BY remind_at ASC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    else:
        rows = cur.execute(
            """
            SELECT * FROM followup_reminders
            ORDER BY
              CASE status WHEN 'due' THEN 0 WHEN 'pending' THEN 1 WHEN 'snoozed' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
              remind_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_due_followups(mark_due: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
    now = _now()
    conn = connect()
    cur = conn.cursor()
    limit = max(1, min(_safe_int(limit, 100), 500))
    if mark_due:
        cur.execute(
            """
            UPDATE followup_reminders
            SET status='due', triggered_at=COALESCE(triggered_at, ?)
            WHERE status IN ('pending','snoozed') AND remind_at <= ?
            """,
            (now, now),
        )
        conn.commit()
    rows = cur.execute(
        """
        SELECT * FROM followup_reminders
        WHERE status='due' OR (status IN ('pending','snoozed') AND remind_at <= ?)
        ORDER BY remind_at ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_followup_status(followup_id: Any, status: str) -> Dict[str, Any]:
    allowed = {"pending", "due", "done", "dismissed", "snoozed"}
    status = (status or "").strip().lower()
    if status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    fid = _safe_int(followup_id)
    if fid <= 0:
        raise ValueError("valid followup id is required")
    completed_at = _now() if status in {"done", "dismissed"} else None
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE followup_reminders
        SET status=?, completed_at=?
        WHERE id=?
        """,
        (status, completed_at, fid),
    )
    conn.commit()
    row = cur.execute("SELECT * FROM followup_reminders WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("followup not found")
    return {"status": "updated", "followup": dict(row)}


def snooze_followup(followup_id: Any, seconds: int = 3600) -> Dict[str, Any]:
    fid = _safe_int(followup_id)
    seconds = max(60, min(_safe_int(seconds, 3600), 30 * 24 * 3600))
    if fid <= 0:
        raise ValueError("valid followup id is required")
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE followup_reminders
        SET status='snoozed', remind_at=?, triggered_at=NULL, completed_at=NULL
        WHERE id=?
        """,
        (_now() + seconds, fid),
    )
    conn.commit()
    row = cur.execute("SELECT * FROM followup_reminders WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("followup not found")
    return {"status": "snoozed", "followup": dict(row)}


def suggest_followup_from_email(email: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    analysis = analysis or {}
    text = " ".join([
        str(email.get("subject") or ""),
        str(email.get("snippet") or ""),
        str(email.get("body") or "")[:1200],
        str(analysis.get("reason") or ""),
    ]).lower()
    action_words = ["reply", "respond", "send", "share", "review", "approve", "confirm", "schedule", "follow up", "deadline", "due"]
    no_reply_words = ["newsletter", "promotion", "unsubscribe", "receipt", "auto-reply", "do not reply"]
    if any(w in text for w in no_reply_words) and not any(w in text for w in ["deadline", "due", "confirm"]):
        return {"should_create": False, "reason": "Looks informational or promotional."}
    if any(w in text for w in action_words) or analysis.get("respond_recommended"):
        return {
            "should_create": True,
            "reason": "Email appears to need a response, review, or follow-up.",
            "suggested_remind_at": _now() + 4 * 3600,
            "note": "Follow up on this email.",
        }
    return {"should_create": False, "reason": "No clear follow-up need detected."}
