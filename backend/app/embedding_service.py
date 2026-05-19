from typing import Optional, List
from app.llm_clients import ollama_embed

def embed_text(text: str) -> Optional[List[float]]:
    return ollama_embed(text)