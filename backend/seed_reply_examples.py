"""
seed_reply_examples.py

Seeds 200 behavioral IN→OUT reply examples into your SQLite RAG DB used by the reply agent.
Works WITHOUT API access.

- Inserts into ./reply_rag.sqlite by default (or REPLY_RAG_DB env var)
- Embeds inbox_text using Ollama embeddings if available (OLLAMA_BASE + OLLAMA_EMBED_MODEL)
- Falls back to a lightweight hash embedding if embeddings model isn't available

Run (from backend folder):
  python seed_reply_examples.py

Optional env vars (PowerShell):
  $env:REPLY_RAG_DB=".\reply_rag.sqlite"
  $env:OLLAMA_BASE="http://127.0.0.1:11434"
  $env:OLLAMA_EMBED_MODEL="nomic-embed-text"
"""

import os
import json
import math
import time
import uuid
import sqlite3
from typing import Any, Dict, List, Tuple

try:
    import requests  # type: ignore
except Exception:
    requests = None  # fallback will still work


DB_PATH = os.getenv("REPLY_RAG_DB", "./reply_rag.sqlite")
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


# -----------------------------
# DB
# -----------------------------
def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reply_examples (
                id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                inbox_text TEXT NOT NULL,
                outbox_text TEXT NOT NULL,
                meta_json TEXT NOT NULL,
                inbox_embed_json TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reply_examples_created
            ON reply_examples(created_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_example(
    conn: sqlite3.Connection,
    ex_id: str,
    inbox_text: str,
    outbox_text: str,
    meta: Dict[str, Any],
    inbox_embed: List[float],
) -> None:
    conn.execute(
        """
        INSERT INTO reply_examples (id, created_at, inbox_text, outbox_text, meta_json, inbox_embed_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            inbox_text=excluded.inbox_text,
            outbox_text=excluded.outbox_text,
            meta_json=excluded.meta_json,
            inbox_embed_json=excluded.inbox_embed_json
        """,
        (
            ex_id,
            int(time.time()),
            inbox_text,
            outbox_text,
            json.dumps(meta, ensure_ascii=False),
            json.dumps(inbox_embed),
        ),
    )


# -----------------------------
# Embedding
# -----------------------------
def hash_embed(text: str, dim: int = 512) -> List[float]:
    v = [0.0] * dim
    for tok in (text or "").lower().split():
        h = 2166136261
        for ch in tok:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        v[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def ollama_embed(text: str) -> List[float]:
    if requests is None:
        raise RuntimeError("requests not available")
    r = requests.post(
        f"{OLLAMA_BASE}/api/embeddings",
        json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    emb = data.get("embedding")
    if not isinstance(emb, list) or not emb:
        raise RuntimeError("Invalid embedding response")
    return [float(x) for x in emb]


def embed(text: str) -> Tuple[List[float], str]:
    text = (text or "").strip()
    if not text:
        return ([0.0] * 512, "empty")
    # try ollama
    try:
        vec = ollama_embed(text)
        return (vec, f"ollama:{OLLAMA_EMBED_MODEL}")
    except Exception:
        return (hash_embed(text, 512), "hash512")


# -----------------------------
# Dataset generation (behavioral)
# -----------------------------
def mk_id(inbox_text: str, outbox_text: str, meta: Dict[str, Any]) -> str:
    # deterministic id so reruns don't create duplicates
    base = inbox_text.strip() + "\n---\n" + outbox_text.strip() + "\n---\n" + json.dumps(meta, sort_keys=True)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def make_inbox(subject: str, body: str) -> str:
    return f"Subject: {subject}\nBody: {body}".strip()


def build_examples() -> List[Dict[str, Any]]:
    # Structures (behavioral, not templates)
    STRUCT = {
        "high": ["acknowledge", "act_now", "time_commitment", "clarify_if_needed", "close_short"],
        "medium": ["acknowledge", "answer", "offer_options_or_next_step", "close_short"],
        "low": ["acknowledge", "optional_future_note"],
        "decline": ["acknowledge", "decline_brief", "close_short"],
        "boundary": ["boundary_statement", "verification_request"],
    }

    # Tones
    TONE = {
        "high": ["focused_direct", "calm_controlled", "confident_brief"],
        "medium": ["warm_concise", "professional_clear", "friendly_neutral"],
        "low": ["brief_acknowledge", "friendly_light", "neutral_short"],
        "promo_decline": ["polite_decline", "neutral_decline", "brief_decline"],
        "spam_boundary": ["firm_cautious", "security_first", "no_nonsense"],
    }

    # Scenario pools
    high_scenarios = [
        ("System Down", "Prod is down. Users can’t log in.", "Thanks for flagging this. I’m looking into it now and will update you in 15 minutes. If you’re seeing an error message, please send it."),
        ("Invoice Due Today", "We need payment confirmation by end of day.", "Understood. I’ll review this now and confirm back today. If there’s a specific reference number I should use, please share it."),
        ("Client Escalation", "Client is unhappy and wants a response today.", "Got it. I’ll draft a response and send it to you for quick review within the next hour so we can reply today."),
        ("Security Alert", "We detected suspicious activity on an account.", "Thanks—treating this as urgent. I’m checking logs and locking down anything suspicious now. Please confirm which account/email is affected."),
        ("Deadline Shift", "Deadline moved up to tomorrow morning.", "Understood. I’ll prioritize this and share a final version by tomorrow morning. Any must-have points you want included?"),
        ("Recruiter Call Today", "Can you jump on a call in 30 mins?", "Yes—I can do that. Please send the meeting link and confirm the agenda so I’m prepared."),
        ("Key Access", "I need the keys today before 6.", "Yes—I can get you the keys before 6. Where should I leave them or should we meet?"),
        ("Flight Change", "My flight changed; need pickup in 45 mins.", "Got it. I can pick you up. Please share the terminal and exact arrival time."),
        ("Payment Failed", "Card payment failed; order is blocked.", "Thanks for the heads-up. I’ll check the payment status now and update you shortly. Do you have the order ID?"),
        ("Urgent Approval", "Need your approval to proceed today.", "Understood. I’m reviewing it now and will approve or comment within the next hour. If there’s a deadline time, tell me so I don’t miss it."),
    ]

    medium_scenarios = [
        ("Roadmap Sync", "Are you free this week to discuss roadmap?", "Yes. I’m available Wednesday or Thursday afternoon. What time works for you?"),
        ("Status Check", "Any progress on the draft?", "Yes—initial draft is done. I’m doing a final pass and will share it by tomorrow morning."),
        ("Data Question", "Which metric should we use for the dashboard?", "I suggest using the weekly active users metric for consistency. If you want, I can also add a trend line for the past 8 weeks."),
        ("Meeting Follow-up", "Can you send notes from the meeting?", "Sure. I’ll send the notes shortly. Anything specific you want highlighted?"),
        ("Clarify Requirement", "Do we need to support CSV export?", "We can support it. Do you need a simple download or a scheduled export as well?"),
        ("Vendor Intro", "Can you take a look at this vendor proposal?", "Yes, I can review it. Please share the key requirements and any constraints (budget/timeline) so I focus on the right parts."),
        ("Schedule Shift", "Can we move our meeting to next week?", "Yes, that works. Do you prefer early next week or later in the week?"),
        ("Doc Review", "Can you review this document when you get a chance?", "Yes. I’ll review it and leave comments. When do you need feedback by?"),
        ("Access Request", "Can you grant me access to the repo?", "Yes—send me your GitHub username (or email) and I’ll add you."),
        ("Task Assignment", "Can you take ownership of the bug fix?", "Yes, I’ll take it. I’ll start today and update you once I’ve narrowed down the root cause."),
    ]

    low_scenarios = [
        ("FYI Policy Update", "Sharing the updated internal policy doc.", "Thanks for sharing. I’ll review it and reach out if I have questions."),
        ("Newsletter", "Monthly newsletter attached.", "Thanks—received."),
        ("Announcement", "Team outing next month details.", "Sounds good—thanks for the info."),
        ("Receipt", "Your receipt is attached.", "Got it—thanks."),
        ("Reminder", "Reminder: please update your profile.", "Thanks for the reminder. I’ll take care of it."),
        ("Resource Link", "Here’s a link to a helpful guide.", "Thanks—saving this."),
        ("No Subject Ping", "Just checking in.", "All good here—thanks for checking in."),
        ("Shared Calendar", "I added the event to the calendar.", "Perfect—thanks."),
        ("Informational Log", "FYI: nightly job completed successfully.", "Thanks for the update."),
        ("Courtesy Copy", "CC’ing you for visibility.", "Thanks—seen."),
    ]

    promo_scenarios = [
        ("BOGO Offer", "Buy one get one free — limited time. Click here.", ""),  # ignore
        ("Sale Ends Tonight", "Huge discount. Don’t miss out.", ""),  # ignore
        ("Webinar Invite", "Join our webinar to learn about X.", "Thanks for the invite. I’m going to pass for now, but appreciate you reaching out."),
        ("SaaS Outreach", "Our tool will boost your productivity 10x. Book a demo.", "Thanks for reaching out. We’re not evaluating new tools right now, but I appreciate the introduction."),
        ("Partnership Pitch", "Let’s partner — we can bring you leads.", "Appreciate the note. We’re not pursuing partnerships at the moment. If that changes, I’ll reach out."),
        ("Marketing Blast", "Special pricing if you reply today.", ""),  # ignore
        ("Conference Promo", "Discounted tickets for this conference.", ""),  # ignore
        ("Upgrade Plan", "Your account is eligible for an upgrade.", "Thanks. Not interested in upgrading right now."),
        ("Training Course", "Enroll in our course to become certified.", ""),  # ignore
        ("Gift Card Promo", "You’ve been selected for a gift card.", ""),  # ignore
    ]

    spam_scenarios = [
        ("Account Verification", "Click this link to avoid suspension.", "I can’t use external verification links from unknown sources. If this is legitimate, please contact me through an official, verified channel."),
        ("You Won Money", "Send your bank details to claim.", ""),  # no reply
        ("Password Reset", "We need your password to secure your account.", "I can’t share passwords or sensitive info by email. If you’re with support, please use the official support channel and provide a ticket number."),
        ("Crypto Investment", "Guaranteed returns — act now.", ""),  # no reply
        ("Remote Job Scam", "Pay a fee to start immediately.", ""),  # no reply
        ("Document Trap", "Open this attachment to see your invoice.", "I can’t open unexpected attachments from unknown senders. Please resend through a verified address and include details in the email body."),
        ("Impersonation", "Hi, it’s your CEO. Need gift cards urgently.", "I can’t proceed with gift card requests over email. Please confirm via a verified phone call or internal channel."),
        ("Unexpected OTP", "Reply with your OTP code.", "I can’t share OTP codes. If you’re verifying something legitimate, use the official process."),
        ("Malware Link", "Download this security update here.", "I can’t download updates from unverified links. Please share the official vendor page or IT instruction."),
        ("Threat Email", "Pay now or we leak your data.", ""),  # no reply
    ]

    # Build 200 examples: 50 high, 50 medium, 40 low, 30 promo, 30 spam = 200
    # We’ll vary tone/length/intent slightly per repetition.
    examples: List[Dict[str, Any]] = []

    def add_many(category: str, base_list: List[Tuple[str, str, str]], count: int) -> None:
        i = 0
        while len([e for e in examples if e["meta"]["category"] == category]) < count:
            subj, body, reply = base_list[i % len(base_list)]
            # small variations to avoid repeating identical text
            variant = (i // len(base_list)) + 1
            subject = subj if variant == 1 else f"{subj} (follow-up {variant})"
            body_v = body
            if variant % 3 == 0:
                body_v = body + " Please confirm."
            elif variant % 5 == 0:
                body_v = body + " Any update is appreciated."
            inbox_text = make_inbox(subject, body_v)

            # vary reply length slightly where reply is non-empty
            reply_v = reply
            if reply_v and variant % 4 == 0:
                reply_v = reply_v + " Thanks."
            if reply_v and variant % 6 == 0:
                reply_v = reply_v.replace("Thanks", "Appreciate it")

            # meta
            if category == "high":
                meta = {
                    "category": "high",
                    "tone": TONE["high"][i % len(TONE["high"])],
                    "intent": "urgent_action",
                    "length_hint": "2-4_lines",
                    "structure": STRUCT["high"],
                    "do_not": ["Do not use corporate filler", "Do not copy example sentences"],
                }
            elif category == "medium":
                meta = {
                    "category": "medium",
                    "tone": TONE["medium"][i % len(TONE["medium"])],
                    "intent": "coordination_or_update",
                    "length_hint": "1-4_lines",
                    "structure": STRUCT["medium"],
                    "do_not": ["Avoid canned phrases", "Do not copy example sentences"],
                }
            elif category == "low":
                meta = {
                    "category": "low",
                    "tone": TONE["low"][i % len(TONE["low"])],
                    "intent": "acknowledge_only",
                    "length_hint": "1-2_lines",
                    "structure": STRUCT["low"],
                    "do_not": ["No long replies", "Do not over-explain"],
                }
            elif category == "promotional":
                if reply_v.strip() == "":
                    meta = {
                        "category": "promotional",
                        "tone": "ignore_marketing",
                        "intent": "no_response",
                        "length_hint": "none",
                        "structure": [],
                        "do_not": ["Do not engage marketing", "Do not ask questions", "Do not click links"],
                    }
                else:
                    meta = {
                        "category": "promotional",
                        "tone": TONE["promo_decline"][i % len(TONE["promo_decline"])],
                        "intent": "decline_sales",
                        "length_hint": "1-3_lines",
                        "structure": STRUCT["decline"],
                        "do_not": ["No negotiation", "No scheduling demos"],
                    }
            else:  # spam
                if reply_v.strip() == "":
                    meta = {
                        "category": "spam",
                        "tone": "no_reply",
                        "intent": "ignore",
                        "length_hint": "none",
                        "structure": [],
                        "do_not": ["Do not respond", "Do not click links", "Do not open attachments"],
                    }
                else:
                    meta = {
                        "category": "spam",
                        "tone": TONE["spam_boundary"][i % len(TONE["spam_boundary"])],
                        "intent": "security_boundary",
                        "length_hint": "1-3_lines",
                        "structure": STRUCT["boundary"],
                        "do_not": ["Never share secrets", "Never click unknown links", "No sensitive info"],
                    }

            examples.append(
                {
                    "inbox_text": inbox_text,
                    "outbox_text": reply_v,
                    "meta": meta,
                }
            )
            i += 1

    add_many("high", high_scenarios, 50)
    add_many("medium", medium_scenarios, 50)
    add_many("low", low_scenarios, 40)
    add_many("promotional", promo_scenarios, 30)
    add_many("spam", spam_scenarios, 30)

    # ensure exactly 200
    return examples[:200]


# -----------------------------
# Seed runner
# -----------------------------
def main() -> None:
    init_db(DB_PATH)
    examples = build_examples()

    conn = connect(DB_PATH)
    inserted = 0
    updated = 0

    # Quick existence cache
    existing_ids = set()
    try:
        cur = conn.execute("SELECT id FROM reply_examples")
        for (rid,) in cur.fetchall():
            existing_ids.add(rid)
    except Exception:
        pass

    embed_mode_counts: Dict[str, int] = {}

    try:
        for ex in examples:
            inbox_text = ex["inbox_text"]
            outbox_text = ex["outbox_text"]
            meta = ex["meta"]

            ex_id = mk_id(inbox_text, outbox_text, meta)
            vec, mode = embed(inbox_text)
            embed_mode_counts[mode] = embed_mode_counts.get(mode, 0) + 1

            if ex_id in existing_ids:
                updated += 1
            else:
                inserted += 1
                existing_ids.add(ex_id)

            upsert_example(conn, ex_id, inbox_text, outbox_text, meta, vec)

        conn.commit()
    finally:
        conn.close()

    print(f"DB: {os.path.abspath(DB_PATH)}")
    print(f"Examples processed: {len(examples)}")
    print(f"Inserted: {inserted}, Updated: {updated}")
    print("Embedding modes:", embed_mode_counts)
    print("Done.")


if __name__ == "__main__":
    main()