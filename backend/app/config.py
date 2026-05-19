import os
from dataclasses import dataclass
from pathlib import Path

def _env(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default

APP_DIR = Path(__file__).resolve().parent        # .../backend/app
BASE_DIR = APP_DIR.parent                        # .../backend

def _resolve_path(p: str) -> str:
    if not p:
        return ""
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    return str((BASE_DIR / pp).resolve())

@dataclass(frozen=True)
class Settings:
    # LLM
    LLM_PROVIDER: str = _env("LLM_PROVIDER", "ollama").lower()  # ollama | openai | none

    # Ollama (FREE local)
    # Backward compatible: support OLLAMA_URL too
    OLLAMA_HOST: str = _env("OLLAMA_HOST", _env("OLLAMA_URL", "http://127.0.0.1:11434"))

    # ✅ Optimal for your CPU-only 16GB laptop (stable + fast)
    OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "qwen2.5:3b-instruct")

    OLLAMA_EMBED_MODEL: str = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # ✅ 20s is too small on CPU; increase for stability
    OLLAMA_TIMEOUT: int = int(_env("OLLAMA_TIMEOUT", "45"))

    # OpenAI (unused in $0 mode, keep for later)
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-4o-mini")

    # Gmail OAuth (absolute-safe)
    GMAIL_CREDENTIALS_PATH: str = _resolve_path(_env("GMAIL_CREDENTIALS_PATH", "credentials/credentials.json"))
    GMAIL_TOKEN_PATH: str = _resolve_path(_env("GMAIL_TOKEN_PATH", "credentials/token.json"))

    # DB (absolute-safe)
    DB_PATH: str = _resolve_path(_env("DB_PATH", "data/app.db"))

    # Thresholds
    THRESH_HIGH: float = float(_env("THRESH_HIGH", "0.80"))
    THRESH_MED: float = float(_env("THRESH_MED", "0.55"))

settings = Settings()