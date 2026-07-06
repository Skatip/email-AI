from typing import Any, Dict


def analyze_email_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_email_body
    from app.priority_engine import priority_score
    from app.utils import parse_sender
    from app.learning import predict_user_preference, apply_user_override
    from app.db import upsert_sender
    from app.analytics_service import track_email_event

    email = payload.get("email") or {}
    provider = payload.get("provider") or email.get("provider") or "gmail"
    if not email:
        raise ValueError("email required")

    if provider == "gmail" and email.get("id") and not (email.get("body") or "").strip():
        try:
            full = fetch_email_body(email.get("id"))
            email = {**email, **full}
        except Exception as body_err:
            print(f"Analyze body fetch warning: {body_err}")

    po = priority_score(email)
    name, sender_email = parse_sender(email.get("from", ""))
    pref = predict_user_preference(sender_email)
    new_p, new_label, new_rr = apply_user_override(
        po.priority,
        po.label,
        po.respond_recommended,
        pref,
    )

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
        "source_folder": email.get("source_folder", ""),
        "email_type": email.get("email_type", ""),
        "relationship_type": email.get("relationship_type", ""),
        "basic_classification": email.get("basic_classification", {}),
        "attachments": email.get("attachments", []),
        "has_attachments": bool(email.get("attachments", [])),
    }

    try:
        track_email_event(item)
    except Exception as track_err:
        print(f"Analytics track error: {track_err}")

    return item


def reply_generate_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_email_body
    from app.reply_agent import draft_reply

    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    force = bool(payload.get("force", False))
    if not email:
        raise ValueError("email payload is required")

    if (email.get("provider") or analysis.get("provider") or "gmail") == "gmail":
        if not (email.get("body") or "").strip() and email.get("id"):
            try:
                full = fetch_email_body(email.get("id"))
                email = {**email, **full}
            except Exception as body_err:
                print(f"Reply body fetch warning: {body_err}")

    return draft_reply(email, analysis, force)


def multi_reply_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.reply_multi import generate_multi

    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    if not email:
        raise ValueError("email payload is required")
    return generate_multi(email, analysis)


def thread_summary_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_full_thread
    from app.thread_summary_agent import summarize_thread

    thread_id = payload.get("thread_id")
    provider = payload.get("provider", "gmail")
    provided_emails = payload.get("emails") or []

    if provider == "outlook":
        return summarize_thread(provided_emails or [payload.get("email") or {}])

    if not thread_id:
        if provided_emails:
            return summarize_thread(provided_emails)
        raise ValueError("thread_id required")

    emails = fetch_full_thread(thread_id)
    return summarize_thread(emails)


def attachment_analyze_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_gmail_attachment
    from app.attachment_analysis import analyze_attachment_bytes

    provider = payload.get("provider", "gmail")
    message_id = payload.get("message_id") or payload.get("email_id")
    attachment = payload.get("attachment") or {}

    if provider != "gmail":
        raise ValueError("Attachment analysis currently supports Gmail only.")
    if not message_id:
        raise ValueError("message_id is required")

    attachment_id = attachment.get("attachment_id") or payload.get("attachment_id")
    filename = attachment.get("filename") or payload.get("filename") or "attachment"
    mime_type = attachment.get("mime_type") or payload.get("mime_type") or ""

    if not attachment_id:
        raise ValueError("attachment_id is required")

    data = fetch_gmail_attachment(message_id, attachment_id)
    return analyze_attachment_bytes(
        filename,
        mime_type,
        data,
        payload.get("sender_band", ""),
        payload.get("source_folder", ""),
        payload.get("email_subject", ""),
        payload.get("email_sender", ""),
        payload.get("email_snippet", ""),
    )


def compose_notes_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.compose_from_notes_agent import write_from_notes

    return write_from_notes(payload.get("notes"), payload.get("tone", "professional"))


def check_due_followups_workflow(payload: Dict[str, Any] | None = None):
    try:
        from app.followup_service import list_due_followups
        return list_due_followups(mark_due=True, limit=int((payload or {}).get("limit", 100)))
    except Exception as e:
        return {"ok": False, "error": str(e)}
