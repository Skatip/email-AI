from __future__ import annotations

import os
import json
import math
import sqlite3
from typing import Any, Dict, List, Optional

import requests

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB = os.path.abspath(os.path.join(_THIS_DIR, "..", "reply_rag.sqlite"))
RAG_DB_PATH = os.getenv("REPLY_RAG_DB", _DEFAULT_DB)

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434").strip()
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip()


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(len(a)):
        x = float(a[i])
        y = float(b[i])
        dot += x * y
        na += x * x
        nb += y * y

    den = (math.sqrt(na) * math.sqrt(nb)) or 1.0
    return dot / den


def _normalize_text(text: str) -> str:
    text = (text or "").strip()
    return " ".join(text.split())


def embed_text(text: str) -> Optional[List[float]]:
    text = _normalize_text(text)
    if not text:
        return None

    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            return None
        return [float(x) for x in emb]
    except Exception as e:
        print("EMBED ERROR:", str(e))
        return None


def retrieve_examples(
    query_text: str,
    k: int = 4,
    max_scan: int = 3000,
    min_score: float = 0.28,
) -> List[Dict[str, Any]]:
    query_text = _normalize_text(query_text)
    qv = embed_text(query_text)
    if qv is None:
        return []

    conn = None
    try:
        conn = sqlite3.connect(RAG_DB_PATH)
        cur = conn.execute(
            """
            SELECT inbox_text, outbox_text, meta_json, inbox_embed_json, created_at
            FROM reply_examples
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (int(max_scan),),
        )
        rows = cur.fetchall()
    except Exception as e:
        print("RAG READ ERROR:", str(e))
        return []
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    scored: List[Dict[str, Any]] = []
    seen_outbox = set()

    for inbox_text, outbox_text, meta_json, inbox_embed_json, created_at in rows:
        try:
            inbox_text = _normalize_text(inbox_text or "")
            outbox_text = _normalize_text(outbox_text or "")

            if not inbox_text or not outbox_text:
                continue

            ev = json.loads(inbox_embed_json) if inbox_embed_json else None
            if not isinstance(ev, list) or not ev:
                continue

            base_score = _cosine(qv, ev)
            if base_score < float(min_score):
                continue

            meta = json.loads(meta_json) if meta_json else {}
            if not isinstance(meta, dict):
                meta = {}

            score = float(base_score)

            out_len = len(outbox_text.split())
            if 4 <= out_len <= 16:
                score += 0.01

            if str(meta.get("label", "")).strip().lower() == "style":
                score += 0.01

            dedupe_key = outbox_text.lower()
            if dedupe_key in seen_outbox:
                continue
            seen_outbox.add(dedupe_key)

            scored.append(
                {
                    "score": score,
                    "base_score": float(base_score),
                    "inbox_text": inbox_text,
                    "outbox_text": outbox_text,
                    "meta": meta,
                    "created_at": created_at,
                }
            )
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)

    final: List[Dict[str, Any]] = []
    seen_prefix = set()

    for row in scored:
        outbox = row["outbox_text"]
        prefix = outbox.lower()[:36]
        if prefix in seen_prefix:
            continue
        seen_prefix.add(prefix)
        final.append(row)
        if len(final) >= max(1, int(k)):
            break

    return final