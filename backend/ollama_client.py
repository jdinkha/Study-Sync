# backend/ollama_client.py
import requests

OLLAMA_BASE = "http://localhost:11434"
MODEL = "mistral"  # fast, 7B, good quality

async def generate_cards(text: str) -> list[dict]:
    prompt = f"""Generate 3 flashcards from this text. Return JSON only.
{text}

[{{"front": "...", "back": "..."}}]"""
    
    response = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=60
    )
    
    result = response.json()
    return parse_json(result["response"])
