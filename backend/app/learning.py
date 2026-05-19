from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

LABELS = ["IMPORTANT", "LESS", "SPAM", "PROMO"]

DEFAULT_STORE_PATH = os.environ.get(
    "LEARNING_STORE_PATH",
    os.path.join(os.path.dirname(__file__), "app_data", "learning_store.json"),
)

def _now() -> int:
    return int(time.time())

def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)

def _load_store(path: str = DEFAULT_STORE_PATH) -> Dict[str, Any]:
    _ensure_dir(path)
    if not os.path.exists(path):
        return {"version": 1, "senders": {}, "domains": {}, "events": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "senders": {}, "domains": {}, "events": []}

def _save_store(store: Dict[str, Any], path: str = DEFAULT_STORE_PATH) -> None:
    _ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _get_domain(sender_email: str) -> str:
    s = (sender_email or "").lower().strip()
    if "@" not in s:
        return ""
    return s.split("@", 1)[1].strip()

def _init_bucket(store: Dict[str, Any], bucket: str, key: str) -> Dict[str, Any]:
    store.setdefault(bucket, {})
    if key not in store[bucket]:
        store[bucket][key] = {"counts": {k: 0 for k in LABELS}, "total": 0, "last_ts": 0}
    else:
        c = store[bucket][key].get("counts", {})
        for k in LABELS:
            c.setdefault(k, 0)
        store[bucket][key]["counts"] = c
        store[bucket][key].setdefault("total", 0)
        store[bucket][key].setdefault("last_ts", 0)
    return store[bucket][key]

def record_feedback(
    *,
    email_id: str,
    sender_email: str,
    clicked: str,
    subject: str = "",
    snippet: str = "",
    meta: Optional[Dict[str, Any]] = None,
    ts: Optional[int] = None,
    path: str = DEFAULT_STORE_PATH,
) -> Dict[str, Any]:
    clicked = (clicked or "").upper().strip()
    if clicked not in LABELS:
        raise ValueError(f"clicked must be one of {LABELS}")

    sender_email = (sender_email or "").lower().strip()
    sender_domain = _get_domain(sender_email)

    store = _load_store(path)
    t = int(ts or _now())

    if sender_email:
        row = _init_bucket(store, "senders", sender_email)
        row["counts"][clicked] += 1
        row["total"] += 1
        row["last_ts"] = t

    if sender_domain:
        row = _init_bucket(store, "domains", sender_domain)
        row["counts"][clicked] += 1
        row["total"] += 1
        row["last_ts"] = t

    ev = {
        "ts": t,
        "email_id": email_id,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "clicked": clicked,
        "subject": subject or "",
        "snippet": (snippet or "")[:300],
        "meta": meta or {},
    }
    store.setdefault("events", [])
    store["events"].append(ev)
    if len(store["events"]) > 2000:
        store["events"] = store["events"][-2000:]

    _save_store(store, path)
    return {"ok": True, "stored": ev}

def _posterior_best(counts: Dict[str, int], alpha: float = 1.0) -> Tuple[str, float]:
    total = sum(int(counts.get(k, 0)) for k in LABELS)
    denom = total + alpha * len(LABELS)
    probs = {k: (counts.get(k, 0) + alpha) / denom for k in LABELS}
    best = max(probs.items(), key=lambda kv: kv[1])
    return best[0], float(best[1])

def predict_user_preference(sender_email: str, *, path: str = DEFAULT_STORE_PATH) -> Optional[Dict[str, Any]]:
    sender_email = (sender_email or "").lower().strip()
    if not sender_email:
        return None

    domain = _get_domain(sender_email)
    store = _load_store(path)

    sender_row = store.get("senders", {}).get(sender_email)
    domain_row = store.get("domains", {}).get(domain) if domain else None

    # anti-misclick guards
    min_evidence_sender = 3
    min_evidence_domain = 5
    min_conf = 0.70

    candidates = []

    if sender_row and int(sender_row.get("total", 0)) >= min_evidence_sender:
        b, c = _posterior_best(sender_row.get("counts", {}))
        candidates.append(("sender", b, c, int(sender_row.get("total", 0))))

    if domain_row and int(domain_row.get("total", 0)) >= min_evidence_domain:
        b, c = _posterior_best(domain_row.get("counts", {}))
        candidates.append(("domain", b, c, int(domain_row.get("total", 0))))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[2], reverse=True)
    source, label, conf, total = candidates[0]
    if conf < min_conf:
        return None

    return {
        "user_category": label,
        "user_category_confidence": conf,
        "user_category_source": source,
        "user_category_evidence": total,
    }

def apply_user_override(
    priority: float,
    label: str,
    respond_recommended: bool,
    pref: Optional[Dict[str, Any]],
) -> Tuple[float, str, bool]:
    if not pref:
        return float(priority or 0.0), (label or "LOW").upper(), bool(respond_recommended)

    cat = (pref.get("user_category") or "").upper()
    conf = float(pref.get("user_category_confidence", 0.0))

    p = float(priority or 0.0)
    lab = (label or "LOW").upper()
    rr = bool(respond_recommended)

    if cat in ("SPAM", "PROMO"):
        p = max(0.0, p - (0.22 + 0.08 * conf))
        lab = "LOW"
        rr = False

    elif cat == "IMPORTANT":
        p = min(1.0, p + (0.10 + 0.06 * conf))
        if lab == "LOW":
            lab = "MEDIUM"
        if p >= 0.85:
            lab = "HIGH"
        rr = True

    elif cat == "LESS":
        p = max(0.0, p - (0.06 + 0.03 * conf))
        if lab == "HIGH":
            lab = "MEDIUM"

    return p, lab, rr