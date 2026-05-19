from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
import asyncio
import time
import threading
import os
from dotenv import load_dotenv

load_dotenv()

from app.db import init_db, kv_get, kv_set, upsert_sender
from app.gmail_service import fetch_emails, fetch_full_thread, fetch_inbox_fast, fetch_email_body
from app.outlook_service import fetch_outlook_emails
from app.priority_engine import priority_score
from app.utils import parse_sender
from app.reply_agent import draft_reply, save_rag_example
from app.reply_multi import generate_multi
from app.learning import predict_user_preference, apply_user_override, record_feedback
from app.thread_summary_agent import summarize_thread
from app.compose_from_notes_agent import write_from_notes
from app.analytics_service import track_email_event, get_analytics_summary

try:
    from app.followup_service import create_followup, list_followups, list_due_followups, update_followup_status
except Exception:
    from app.followup_service import create_followup, list_followups
    list_due_followups = None
    update_followup_status = None

app = FastAPI(title="Email Priority Backend", version="1.9.0-fast-inbox")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FOCUSED_GMAIL_QUERY = (
    "{category:primary in:spam} "
    "-category:promotions -category:social -category:forums "
    "-unsubscribe"
)


def _effective_query(user_query: str) -> str:
    q = (user_query or "").strip()
    return f"{FOCUSED_GMAIL_QUERY} {q}".strip() if q else FOCUSED_GMAIL_QUERY


def _labels_text(item: Dict[str, Any]) -> str:
    labels = item.get("labelIds") or item.get("labels") or []
    return " ".join(str(x).lower() for x in labels)


def _quick_human_filter(item: Dict[str, Any]) -> bool:
    """Cheap filter only. No AI. Keeps primary emails and human-like spam."""
    sender = (item.get("from") or "").lower()
    subject = (item.get("subject") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    text = f"{subject} {snippet}"
    labels = _labels_text(item)
    is_spam = "spam" in labels

    blocked_sender = [
        "no-reply", "noreply", "donotreply", "do-not-reply",
        "newsletter", "notifications@", "notification@",
        "mail.dave.com", "dave.com", "cashapp", "chime", "earnin", "brigit", "cleo",
        "linkedin", "indeed", "glassdoor", "dice", "salesforce", "hotlist",
    ]
    blocked_text = [
        "unsubscribe", "manage preferences", "verify your email", "verification code",
        "cash advance", "extra cash", "debit card", "bank account",
        "promo", "promotion", "discount", "offer expires", "newsletter",
        "job alert", "hotlist", "c2c", "bench sales",
    ]
    human_words = [
        "can we", "could you", "please", "need to", "wanted to", "let me know",
        "available", "meeting", "call", "talk", "discuss", "project", "question",
        "help", "follow up", "update", "send me", "share", "reply", "urgent",
    ]

    if any(x in sender for x in blocked_sender):
        return False
    if any(x in text for x in blocked_text):
        return False

    if is_spam:
        return any(x in text for x in human_words) and not any(x in sender for x in blocked_sender)

    return True


_ANALYZE_CACHE: Dict[str, Any] = {}
_ANALYZE_CACHE_LOCK = threading.Lock()
_ANALYZE_CACHE_TTL = 30


def _cache_get(key: str):
    now = time.time()
    with _ANALYZE_CACHE_LOCK:
        item = _ANALYZE_CACHE.get(key)
        if not item:
            return None
        exp, value = item
        if exp < now:
            _ANALYZE_CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value):
    with _ANALYZE_CACHE_LOCK:
        _ANALYZE_CACHE[key] = (time.time() + _ANALYZE_CACHE_TTL, value)


def _clear_cache():
    with _ANALYZE_CACHE_LOCK:
        _ANALYZE_CACHE.clear()


@app.on_event("startup")
def _startup():
    init_db()
    if kv_get("last_seen_ts") is None:
        kv_set("last_seen_ts", "0")


@app.get("/inbox")
async def inbox_fast(
    user_email: str = Query(default=""),
    query: str = Query(default=""),
    max_results: int = Query(default=10),
    provider: str = Query(default="gmail"),
):
    """
    FAST dashboard endpoint.
    Returns email cards immediately with metadata/snippet only.
    No priority_score, no body fetch, no RAG, no Ollama.
    """
    cache_key = f"inbox|{provider}|{user_email}|{query}|{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        if provider == "outlook":
            app_pwd = os.getenv("OUTLOOK_APP_PASSWORD")
            if not app_pwd:
                raise HTTPException(status_code=500, detail="OUTLOOK_APP_PASSWORD not found in .env")
            raw = await asyncio.to_thread(
                fetch_outlook_emails,
                email_user=user_email,
                app_password=app_pwd,
                max_results=max_results,
            )
        else:
            raw = await asyncio.to_thread(
                fetch_inbox_fast,
                query=_effective_query(query),
                max_results=max(max_results * 3, 30),
                scan_limit=max(max_results * 8, 80),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fast inbox fetch failed: {str(e)}")

    out: List[Dict[str, Any]] = []
    for e in raw:
        if provider == "gmail" and not _quick_human_filter(e):
            continue
        out.append({
            "id": e.get("id"),
            "threadId": e.get("threadId"),
            "from": e.get("from", ""),
            "subject": e.get("subject", ""),
            "snippet": e.get("snippet", ""),
            "body": "",
            "ts": e.get("ts", 0),
            "labelIds": e.get("labelIds") or e.get("labels") or [],
            "provider": provider,
            "priority": 0.0,
            "label": "PENDING",
            "risk": 0.0,
            "sender_band": "PENDING",
            "intent": "pending",
            "reason": "Email loaded fast. AI analysis is running in background.",
            "respond_recommended": False,
            "human_signals": {},
            "analysis_status": "pending",
            "mail_scope": "FAST_PRIMARY_AND_HUMAN_SPAM" if provider == "gmail" else "FAST_INBOX",
        })
        if len(out) >= max_results:
            break

    _cache_set(cache_key, out)
    return out


@app.post("/email/analyze")
async def email_analyze(payload: Dict[str, Any] = Body(...)):
    """Analyze one email after it is already rendered in UI."""
    email = payload.get("email") or {}
    provider = payload.get("provider") or email.get("provider") or "gmail"

    if not email:
        raise HTTPException(status_code=400, detail="email required")

    try:
        if provider == "gmail" and email.get("id") and not (email.get("body") or "").strip():
            try:
                full = await asyncio.to_thread(fetch_email_body, email.get("id"))
                email = {**email, **full}
            except Exception as body_err:
                print(f"Analyze body fetch warning: {body_err}")

        po = await asyncio.to_thread(priority_score, email)
        name, sender_email = parse_sender(email.get("from", ""))
        pref = predict_user_preference(sender_email)
        new_p, new_label, new_rr = apply_user_override(po.priority, po.label, po.respond_recommended, pref)

        try:
            upsert_sender(sender_email, name, new_p, new_label, int(email.get("ts", 0)))
        except Exception:
            pass

        item = {
            **email,
            "priority": new_p,
            "label": new_label,
            "reason": po.reason,
            "intent": po.intent,
            "sender_band": po.sender_band,
            "risk": po.risk,
            "coherence": po.coherence,
            "coherence_band": getattr(po, "coherence_band", None),
            "respond_recommended": new_rr,
            "user_pref": pref,
            "urgency_minutes": getattr(po, "urgency_minutes", None),
            "human_signals": getattr(po, "human_signals", None),
            "risk_signals": (getattr(po, "human_signals", None) or {}).get("risk_signals", []),
            "risk_reasons": (getattr(po, "human_signals", None) or {}).get("risk_reasons", []),
            "risk_urls": (getattr(po, "human_signals", None) or {}).get("risk_urls", []),
            "provider": provider,
            "analysis_status": "done",
        }

        try:
            track_email_event(item)
        except Exception as track_err:
            print(f"Analytics track error: {track_err}")

        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email analysis failed: {str(e)}")


@app.get("/analyze")
async def analyze(
    user_email: str = Query(default=""),
    query: str = Query(default=""),
    max_results: int = Query(default=10),
    include_thread_context: bool = Query(default=False),
    include_reply: bool = Query(default=False),
    reply_top_n: int = Query(default=0),
    provider: str = Query(default="gmail"),
):
    """Backward compatible endpoint. Now uses fast inbox + per-email analysis."""
    base = await inbox_fast(user_email=user_email, query=query, max_results=max_results, provider=provider)
    analyzed = []
    for email in base:
        try:
            item = await email_analyze({"email": email, "provider": provider})
        except Exception:
            item = email
        analyzed.append(item)
    return analyzed


@app.post("/reply/generate")
async def reply_generate(payload: Dict[str, Any] = Body(...)):
    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    force = bool(payload.get("force", False))
    if not email:
        raise HTTPException(status_code=400, detail="email payload is required")
    try:
        if (email.get("provider") or analysis.get("provider") or "gmail") == "gmail":
            if not (email.get("body") or "").strip() and email.get("id"):
                try:
                    full = await asyncio.to_thread(fetch_email_body, email.get("id"))
                    email = {**email, **full}
                except Exception as body_err:
                    print(f"Reply body fetch warning: {body_err}")
        return await asyncio.to_thread(draft_reply, email, analysis, force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reply generation failed: {str(e)}")


@app.post("/reply/multi")
def multi_reply(payload: Dict[str, Any] = Body(...)):
    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    if not email:
        raise HTTPException(status_code=400, detail="email payload is required")
    return generate_multi(email, analysis)


@app.post("/reply/save_example")
def reply_save_example(payload: Dict[str, Any] = Body(...)):
    inbound = (payload.get("inbound") or "").strip()
    outbound = (payload.get("outbound") or "").strip()
    label = (payload.get("label") or "style").strip() or "style"
    if not inbound or not outbound:
        raise HTTPException(status_code=400, detail="inbound and outbound required")
    return save_rag_example(inbound, outbound, label=label)


@app.post("/feedback")
def feedback(payload: Dict[str, Any] = Body(...)):
    sender_email = (payload.get("sender_email") or "").strip()
    clicked = (payload.get("clicked") or "").strip().upper()
    if not sender_email:
        raise HTTPException(status_code=400, detail="sender_email is required")
    if not clicked:
        raise HTTPException(status_code=400, detail="clicked is required")
    result = record_feedback(
        email_id=(payload.get("email_id") or "").strip(),
        sender_email=sender_email,
        clicked=clicked,
        subject=payload.get("subject") or "",
        snippet=payload.get("snippet") or "",
        meta=payload.get("meta") or {},
    )
    _clear_cache()
    return result


@app.get("/thread/full")
async def thread_full(thread_id: str, provider: str = Query(default="gmail")):
    if provider == "outlook":
        raise HTTPException(status_code=400, detail="Outlook full thread not added yet")
    return {"thread": await asyncio.to_thread(fetch_full_thread, thread_id)}


@app.post("/thread/summary")
async def thread_summary_api(payload: Dict[str, Any] = Body(...)):
    thread_id = payload.get("thread_id")
    provider = payload.get("provider", "gmail")
    provided_emails = payload.get("emails") or []
    if provider == "outlook":
        return await asyncio.to_thread(summarize_thread, provided_emails or [payload.get("email") or {}])
    if not thread_id:
        if provided_emails:
            return await asyncio.to_thread(summarize_thread, provided_emails)
        raise HTTPException(status_code=400, detail="thread_id required")
    emails = await asyncio.to_thread(fetch_full_thread, thread_id)
    return await asyncio.to_thread(summarize_thread, emails)


@app.post("/followups/create")
def followup_create(payload: Dict[str, Any] = Body(...)):
    try:
        return create_followup(
            email_id=payload.get("email_id"),
            thread_id=payload.get("thread_id", ""),
            remind_at=payload.get("remind_at"),
            note=payload.get("note", ""),
            subject=payload.get("subject", ""),
            sender=payload.get("sender", ""),
            provider=payload.get("provider", "gmail"),
        )
    except TypeError:
        return create_followup(payload.get("email_id"), payload.get("remind_at"), payload.get("note", ""))


@app.get("/followups")
def followups(status: str = Query(default=""), limit: int = Query(default=100)):
    try:
        return list_followups(status=status or None, limit=limit)
    except TypeError:
        return list_followups()


@app.get("/followups/due")
def followups_due(limit: int = Query(default=100)):
    if list_due_followups is None:
        return []
    return list_due_followups(mark_due=True, limit=limit)


@app.post("/followups/{followup_id}/status")
def followup_status(followup_id: int, payload: Dict[str, Any] = Body(...)):
    if update_followup_status is None:
        raise HTTPException(status_code=400, detail="Followup status update not available")
    return update_followup_status(followup_id, payload.get("status"))


@app.post("/compose/from-notes")
def compose_notes(payload: Dict[str, Any] = Body(...)):
    return write_from_notes(payload.get("notes"), payload.get("tone", "professional"))


@app.get("/analytics")
def analytics(days: int = Query(default=14)):
    try:
        return get_analytics_summary(days=days)
    except TypeError:
        return get_analytics_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok", "mode": "fast_inbox_async_analysis"}


@app.get("/")
def root():
    return {"message": "AI Email Backend running", "mode": "fast_inbox_async_analysis"}
