import os
import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_GEN_MODEL", "gpt-oss:120b-cloud")

def write_from_notes(notes, tone="professional"):
    prompt = f"""
Write a clean email.

Tone: {tone}

Notes:
{notes}
"""

    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=60
    )

    return {"email": r.json().get("response", "")}