from __future__ import annotations

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


def create_followup(
    email_id: str,
    remind_at: Any,
    note: str = "",
    thread_id: str = "",
    subject: str = "",
    sender: str = "",
    provider: str = "gmail",
) -> Dict[str, Any]:
    if not email_id:
        raise ValueError("email_id is required")

    remind_ts = _safe_int(remind_at)
    if remind_ts <= 0:
        remind_ts = _now() + 3600

    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO followup_reminders(
            email_id, thread_id, remind_at, status, note, created_at,
            subject, sender, provider, triggered_at, completed_at
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            email_id,
            thread_id or "",
            remind_ts,
            "pending",
            note or "",
            _now(),
            subject or "",
            sender or "",
            provider or "gmail",
            None,
            None,
        ),
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
              CASE status WHEN 'due' THEN 0 WHEN 'pending' THEN 1 WHEN 'done' THEN 2 ELSE 3 END,
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
            WHERE status='pending' AND remind_at <= ?
            """,
            (now, now),
        )
        conn.commit()

    rows = cur.execute(
        """
        SELECT * FROM followup_reminders
        WHERE status IN ('due','pending') AND remind_at <= ?
        ORDER BY remind_at ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def update_followup_status(followup_id: Any, status: str) -> Dict[str, Any]:
    allowed = {"pending", "due", "done", "dismissed"}
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
