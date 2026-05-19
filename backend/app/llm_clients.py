import os
import json
from typing import Any, Dict, Optional

import requests

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")


def chat_json(system: str, user_prompt: str, schema_hint: str) -> Optional[Dict[str, Any]]:
    payload = {
        "model": OLLAMA_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"{user_prompt}\n\nSCHEMA:\n{schema_hint}\n\nReturn JSON ONLY.",
            },
        ],
        "format": "json",
        "options": {
            "temperature": 0.25,
            "num_predict": 450,
        },
        "stream": False,
    }

    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        text = ((data.get("message") or {}).get("content") or "").strip()
        if not text:
            return None
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def chat(system: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 80) -> str:
    payload = {
        "model": OLLAMA_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": float(temperature),
            "num_predict": int(max_tokens),
            "top_p": 0.9,
            "stop": ["User:", "Assistant:", "Note:", "Reasoning:"],
        },
        "stream": False,
    }

    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        return ((data.get("message") or {}).get("content") or "").strip()
    except Exception:
        return ""