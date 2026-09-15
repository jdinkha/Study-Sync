from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
import json
import re
import os
import tempfile
import datetime
import uuid
import random
from pathlib import Path

import pymupdf
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, text
from sqlalchemy.orm import declarative_base, Session, sessionmaker

load_dotenv()  # reads .env file if present

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")  # fallback to mistral if not set

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./studysync.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Deck(Base):
    __tablename__ = "decks"
    id = Column(String, primary_key=True)
    userId = Column(String, default="user1")
    name = Column(String)
    createdAt = Column(DateTime, default=datetime.datetime.utcnow)

class Card(Base):
    __tablename__ = "cards"
    id = Column(String, primary_key=True)
    deckId = Column(String)
    front = Column(String)
    back = Column(String)
    choices = Column(String, nullable=True)  # JSON-encoded list of 4 multiple-choice options
    ef = Column(Float, default=2.5)
    interval = Column(Integer, default=0)
    reps = Column(Integer, default=0)
    dueAt = Column(DateTime, default=datetime.datetime.utcnow)

class ReviewLog(Base):
    __tablename__ = "review_logs"
    id = Column(String, primary_key=True)
    cardId = Column(String)
    quality = Column(Integer)
    intervalAfter = Column(Integer)
    reviewedAt = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Migrate older sqlite files created before the "choices" column existed
with engine.connect() as conn:
    existing_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(cards)"))]
    if "choices" not in existing_cols:
        conn.execute(text("ALTER TABLE cards ADD COLUMN choices TEXT"))
        conn.commit()

class ReviewRequest(BaseModel):
    cardId: str
    quality: int

# ── Utilities ──────────────────────────────────────────────────────────────────

async def extract_text_from_pdf(filepath: str) -> list[str]:
    doc = pymupdf.open(filepath)
    chunks = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            chunks.append(text)
    doc.close()
    return chunks

def extract_valid_cards(cards) -> list[dict]:
    """Validate a parsed JSON array into multiple-choice card dicts."""
    valid = []
    if not isinstance(cards, list):
        return valid
    for c in cards:
        if not isinstance(c, dict):
            continue
        front = str(c.get("front", "")).strip()
        choices = c.get("choices")
        answer = str(c.get("answer", "")).strip()

        if not front or front == "?" or not isinstance(choices, list) or len(choices) != 4:
            continue

        choices = [str(ch).strip() for ch in choices]
        if any(not ch or ch == "?" for ch in choices):
            continue

        # The answer must be the exact text of one of the choices
        match = next((ch for ch in choices if ch.lower() == answer.lower()), None)
        if not match:
            continue

        valid.append({"front": front, "choices": choices, "answer": match})
    return valid

def shuffle_choices(choices: list[str]) -> list[str]:
    """Shuffle choice order, but keep "All of the above" pinned as the last option."""
    def is_all_of_above(s: str) -> bool:
        return s.strip().rstrip(".").lower() == "all of the above"

    pinned = [c for c in choices if is_all_of_above(c)]
    rest = [c for c in choices if not is_all_of_above(c)]
    random.shuffle(rest)
    return rest + pinned

def parse_ollama_response(text: str) -> list[dict]:
    """Parse JSON from Ollama, being very defensive about malformed input."""
    text = text.strip()

    # Strip markdown code fences
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try to find and extract the JSON array
    start = text.find('[')
    end = text.rfind(']')

    if start == -1 or end == -1 or start >= end:
        print(f"[PARSE] No JSON array found")
        return []

    raw = text[start:end+1]

    # First attempt: try to parse as-is
    try:
        cards = json.loads(raw)
        valid = extract_valid_cards(cards)
        if valid:
            return valid
    except json.JSONDecodeError:
        pass

    # Second attempt: sanitize newlines inside string values
    def sanitize(s: str) -> str:
        result = []
        in_string = False
        i = 0
        while i < len(s):
            ch = s[i]
            prev = s[i - 1] if i > 0 else ''

            if ch == '"' and prev != '\\':
                in_string = not in_string
                result.append(ch)
            elif in_string and ch in '\n\r\t':
                # Replace control chars with space inside strings
                result.append(' ')
            else:
                result.append(ch)
            i += 1
        return ''.join(result)

    cleaned = sanitize(raw)
    try:
        cards = json.loads(cleaned)
        valid = extract_valid_cards(cards)
        if valid:
            return valid
    except json.JSONDecodeError as e:
        pass

    print(f"[PARSE] Could not extract valid cards from response")
    return []
async def generate_cards_from_chunk(chunk: str) -> list[dict]:
    # Truncate large chunks
    chunk = chunk[:2500]  # smaller for gemma

    # Ultra-strict prompt for small models
    prompt = f"""You are a multiple-choice flashcard generator. Generate exactly 2 flashcards.

CRITICAL RULES:
1. Output ONLY valid JSON. No markdown, no text before or after.
2. Each flashcard has a "front" (the question), a "choices" array of EXACTLY 4 short answer options, and an "answer" field that is the exact text of the one correct choice.
3. Exactly 1 of the 4 choices is correct. The other 3 must be plausible, on-topic, but incorrect.
4. You may occasionally make "All of the above" one of the 4 choices when it fits — use it as the correct "answer" ONLY when the other choices are all individually true (meaning "All of the above" is allowed to be an incorrect option).
5. Keep every choice SHORT: max 12 words, ONE LINE, no newlines, no code blocks.
6. Questions must be clear and specific.

Format (no variations):
[{{"front": "What is X?", "choices": ["Correct answer", "Plausible wrong answer", "Another wrong answer", "A third wrong answer"], "answer": "Correct answer"}}, {{...}}]

Do not output anything else. Do not explain. Just the JSON array.

TEXT TO MAKE FLASHCARDS FROM:
{chunk}

Output the 2 flashcards as JSON only:"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,  # lower temp = stricter, more predictable
                    "options": {"num_predict": 400},  # smaller models need less budget
                },
            )

        if response.status_code != 200:
            print(f"[OLLAMA] Error: {response.text}")
            return []

        result = response.json()
        cards = parse_ollama_response(result.get("response", ""))
        # Shuffle choice order (correct answer isn't always in the same slot),
        # but "All of the above" always stays the last option.
        for card in cards:
            card["choices"] = shuffle_choices(card["choices"])
        return cards

    except Exception as e:
        print(f"[OLLAMA] Exception: {e}")
        return []

def sm2(card: Card, quality: int) -> Card:
    if quality >= 3:
        if card.reps == 0:
            interval = 1
        elif card.reps == 1:
            interval = 6
        else:
            interval = max(1, int(card.interval * card.ef))
        card.reps += 1
    else:
        card.reps = 0
        interval = 1

    card.ef = card.ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    card.ef = max(1.3, card.ef)
    card.interval = interval
    card.dueAt = datetime.datetime.utcnow() + datetime.timedelta(days=interval)
    return card

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/models")
async def list_models():
    """Ask Ollama which models are installed on this machine."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not reach Ollama")
        data = response.json()
        # Ollama returns {"models": [{"name": "mistral:latest", ...}, ...]}
        names = [m["name"] for m in data.get("models", [])]
        return {"models": names, "active": OLLAMA_MODEL}
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Ollama is not running on " + OLLAMA_HOST)

@app.post("/api/config/model")
async def set_model(model: str):
    """Switch the active model at runtime."""
    global OLLAMA_MODEL
    # Verify the model is actually installed before switching
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{OLLAMA_HOST}/api/tags")
    available = [m["name"] for m in response.json().get("models", [])]
    if model not in available:
        raise HTTPException(status_code=400, detail=f"Model '{model}' is not installed. Run: ollama pull {model}")
    OLLAMA_MODEL = model
    print(f"[CONFIG] Switched model to {model}")
    return {"active": OLLAMA_MODEL}

@app.post("/api/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    deckName: str = Form(...),
    userId: str = Form(default="user1")
):
    if not deckName or not deckName.strip():
        raise HTTPException(status_code=400, detail="Deck name is required")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        chunks = await extract_text_from_pdf(tmp_path)
        if not chunks:
            raise HTTPException(status_code=400, detail="No text found in PDF")

        print(f"[INGEST] {len(chunks)} chunks extracted")

        # Create deck and immediately capture the id as a plain string
        deck_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            deck = Deck(id=deck_id, userId=userId, name=deckName.strip())
            db.add(deck)
            db.commit()
        finally:
            db.close()

        print(f"[INGEST] Created deck {deck_id}")

        # Generate cards (outside the db session — this takes a long time)
        all_cards = []
        for i, chunk in enumerate(chunks):
            print(f"[INGEST] Chunk {i+1}/{len(chunks)}")
            cards = await generate_cards_from_chunk(chunk)
            all_cards.extend(cards)
            print(f"[INGEST] Chunk {i+1}/{len(chunks)} → {len(cards)} cards")

        if not all_cards:
            raise HTTPException(status_code=400, detail="Could not generate any cards from PDF")

        # Save cards in a fresh session
        db = SessionLocal()
        try:
            for card_data in all_cards:
                card = Card(
                    id=str(uuid.uuid4()),
                    deckId=deck_id,
                    front=card_data["front"],
                    back=card_data["answer"],
                    choices=json.dumps(card_data["choices"]),
                )
                db.add(card)
            db.commit()
        finally:
            db.close()

        print(f"[INGEST] ✓ Deck {deck_id} done — {len(all_cards)} cards")

        return {
            "deckId": deck_id,
            "cardCount": len(all_cards),
            "message": f"Created deck with {len(all_cards)} cards"
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

@app.get("/api/decks")
async def list_decks(userId: str = "user1"):
    db = SessionLocal()
    try:
        decks = db.query(Deck).filter(Deck.userId == userId).all()
        result = []
        for deck in decks:
            card_count = db.query(Card).filter(Card.deckId == deck.id).count()
            result.append({
                "id": deck.id,
                "name": deck.name,
                "createdAt": deck.createdAt.isoformat(),
                "cardCount": card_count
            })
        return result
    finally:
        db.close()

@app.get("/api/decks/{deckId}")
async def get_deck(deckId: str):
    db = SessionLocal()
    try:
        deck = db.query(Deck).filter(Deck.id == deckId).first()
        if not deck:
            raise HTTPException(status_code=404, detail="Deck not found")
        card_count = db.query(Card).filter(Card.deckId == deckId).count()
        return {
            "id": deck.id,
            "name": deck.name,
            "createdAt": deck.createdAt.isoformat(),
            "cardCount": card_count
        }
    finally:
        db.close()

@app.get("/api/cards/due")
async def get_due_cards(deckId: str):
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        cards = db.query(Card).filter(
            Card.deckId == deckId,
            Card.dueAt <= now
        ).order_by(Card.dueAt).limit(20).all()

        return [{
            "id": c.id,
            "front": c.front,
            "back": c.back,
            "choices": json.loads(c.choices) if c.choices else [],
            "ef": c.ef,
            "interval": c.interval,
            "reps": c.reps
        } for c in cards]
    finally:
        db.close()

@app.post("/api/review")
async def review_card(req: ReviewRequest):
    db = SessionLocal()
    try:
        card = db.query(Card).filter(Card.id == req.cardId).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")

        card = sm2(card, req.quality)
        db.commit()

        log = ReviewLog(
            id=str(uuid.uuid4()),
            cardId=card.id,
            quality=req.quality,
            intervalAfter=card.interval
        )
        db.add(log)
        db.commit()

        return {
            "nextDue": card.dueAt.isoformat(),
            "ef": card.ef,
            "interval": card.interval
        }
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
