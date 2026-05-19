from __future__ import annotations

import os
from typing import Dict, List

import requests


OLLAMA_HOST = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434"))
GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b"))


def _ollama_chat(messages: List[Dict[str, str]], temperature: float = 0.55) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": GEN_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": float(temperature),
                    "top_p": 0.9,
                    "num_predict": 40,
                    "stop": ["User:", "Assistant:", "Note:", "Reasoning:"],
                },
            },
            timeout=45,
        )
        r.raise_for_status()
        return ((r.json().get("message") or {}).get("content") or "").strip()
    except Exception:
        return ""


def generate_candidates(message_sets: List[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    temps = [0.45, 0.65]
    out: List[Dict[str, str]] = []

    for idx, messages in enumerate(message_sets[:2]):
        text = _ollama_chat(messages, temperature=temps[idx])
        out.append(
            {
                "candidate_id": f"c{idx+1}",
                "reply": text,
                "temperature": temps[idx],
                "model": GEN_MODEL,
            }
        )

    return out