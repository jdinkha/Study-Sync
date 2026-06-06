from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import re
import os
import tempfile
import datetime
import uuid
from pathlib import Path

import pymupdf
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.orm import declarative_base, Session, sessionmaker

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

def parse_ollama_response(text: str) -> list[dict]:
    """Parse JSON from Ollama, handling control characters and markdown fences."""
    text = text.strip()

    # Strip markdown code fences
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Find the JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        print(f"[PARSE] No JSON array found in: {text[:200]}")
        return []

    raw = match.group()

    # Fix literal newlines/tabs inside JSON string values (Ollama sometimes does this)
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
            elif in_string:
                if ch == '\n':
                    result.append('\\n')
                elif ch == '\r':
                    result.append('\\r')
                elif ch == '\t':
                    result.append('\\t')
                else:
                    result.append(ch)
            else:
                result.append(ch)
            i += 1
        return ''.join(result)

    cleaned = sanitize(raw)

    try:
        cards = json.loads(cleaned)
        valid = []
        for c in cards:
            if isinstance(c, dict) and c.get("front") and c.get("back"):
                valid.append({
                    "front": str(c["front"]).strip(),
                    "back": str(c["back"]).strip()
                })
        return valid
    except json.JSONDecodeError as e:
        print(f"[PARSE] JSON error: {e} — snippet: {cleaned[:300]}")
        return []

async def generate_cards_from_chunk(chunk: str) -> list[dict]:
    # Truncate large chunks so prompt + response fits in context
    chunk = chunk[:2000]

    prompt = f"""Generate 2 flashcards from this text.

Rules:
- Questions should test understanding (why, how, difference between)
- Answers must be SHORT — 1 sentence max, under 20 words
- Return ONLY a JSON array, no markdown, no explanation
- No newlines inside string values

Format exactly:
[{{"front": "Question?", "back": "Short answer."}}]

Text:
{chunk}"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.2,
                    "options": {"num_predict": 512},
                },
            )

        if response.status_code != 200:
            print(f"[OLLAMA] Error: {response.text}")
            return []

        result = response.json()
        return parse_ollama_response(result.get("response", ""))

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
                    back=card_data["back"],
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
