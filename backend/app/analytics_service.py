from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List

from app.db import connect


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_meta(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _sender_domain(sender: str) -> str:
    sender = sender or ""
    if "<" in sender and ">" in sender:
        sender = sender.split("<", 1)[1].split(">", 1)[0]
    if "@" in sender:
        return sender.split("@", 1)[1].lower().strip()
    return "unknown"


def track_email_event(email: dict) -> None:
    conn = connect()
    cur = conn.cursor()

    metadata = {
        "priority": email.get("priority"),
        "label": email.get("label"),
        "risk": email.get("risk"),
        "intent": email.get("intent"),
        "sender": email.get("from"),
        "provider": email.get("provider", "gmail"),
        "sender_band": email.get("sender_band"),
    }

    cur.execute(
        """
        INSERT INTO email_events (email_id, event_type, metadata, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (email.get("id"), "analyzed", json.dumps(metadata), int(time.time())),
    )

    conn.commit()
    conn.close()


def get_analytics_summary(days: int = 14) -> Dict[str, Any]:
    now = int(time.time())
    since = now - max(1, int(days or 14)) * 86400

    conn = connect()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT email_id, event_type, metadata, created_at
        FROM email_events
        WHERE created_at >= ?
        ORDER BY created_at ASC
        """,
        (since,),
    ).fetchall()
    conn.close()

    total = 0
    high = 0
    medium = 0
    low = 0
    risky = 0
    provider_counts = Counter()
    intent_counts = Counter()
    sender_counts = Counter()
    daily = defaultdict(lambda: {"total": 0, "high": 0, "risky": 0, "avg_priority": 0.0, "avg_risk": 0.0})

    for row in rows:
        meta = _safe_meta(row["metadata"])
        priority = _safe_float(meta.get("priority"))
        risk = _safe_float(meta.get("risk"))
        label = str(meta.get("label") or "").upper()
        intent = str(meta.get("intent") or "general")
        provider = str(meta.get("provider") or "gmail")
        sender = str(meta.get("sender") or "")
        day = time.strftime("%Y-%m-%d", time.localtime(int(row["created_at"] or now)))

        total += 1
        provider_counts[provider] += 1
        intent_counts[intent] += 1
        sender_counts[_sender_domain(sender)] += 1

        if label == "HIGH" or priority >= 0.70:
            high += 1
            daily[day]["high"] += 1
        elif label == "MEDIUM" or priority >= 0.40:
            medium += 1
        else:
            low += 1

        if risk >= 0.50:
            risky += 1
            daily[day]["risky"] += 1

        d = daily[day]
        d["total"] += 1
        d["avg_priority"] += priority
        d["avg_risk"] += risk

    trend: List[Dict[str, Any]] = []
    for day in sorted(daily.keys()):
        d = daily[day]
        count = max(1, int(d["total"]))
        trend.append(
            {
                "date": day,
                "total": d["total"],
                "high": d["high"],
                "risky": d["risky"],
                "avg_priority": round(d["avg_priority"] / count, 3),
                "avg_risk": round(d["avg_risk"] / count, 3),
            }
        )

    return {
        "total": total,
        "high_priority": high,
        "medium_priority": medium,
        "low_priority": low,
        "risky": risky,
        "safe": max(0, total - risky),
        "provider_counts": dict(provider_counts),
        "intent_counts": dict(intent_counts.most_common(10)),
        "top_senders": [{"sender": k, "count": v} for k, v in sender_counts.most_common(8)],
        "daily_trend": trend,
    }
