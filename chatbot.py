import os
import time
import secrets
import logging
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from openai import OpenAI

from databasetwo import SessionLocal, MessageDB

# Load variables from the .env file
load_dotenv(override=True)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler("chatbot.log", maxBytes=1_000_000, backupCount=3),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------- Settings ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
APP_API_KEY = os.getenv("APP_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")
if not APP_API_KEY:
    raise RuntimeError("APP_API_KEY is missing. Add it to your .env file.")

MODEL = "openai/gpt-oss-20b"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

app = FastAPI(title="AI Chatbot API")

# ---------- Authentication ----------
api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(key: str = Security(api_key_header)):
    if not secrets.compare_digest(key, APP_API_KEY):
        logger.warning("Invalid API key attempt")
        raise HTTPException(status_code=401, detail="Invalid API Key")


# ---------- Database ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Schemas ----------
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


# ---------- Routes ----------
@app.post("/chat", dependencies=[Depends(verify_api_key)])
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. Load the last 20 messages of this session
    old = (
        db.query(MessageDB)
        .filter(MessageDB.session_id == req.session_id)
        .order_by(MessageDB.id.desc())
        .limit(20)
        .all()
    )
    old.reverse()  # oldest first

    # 2. Build the message list
    messages = [
        {
            "role": "system",
            "content": "You are a helpful chatbot. Keep answers short and reply in the user's language.",
        }
    ]
    for m in old:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    # 3. Call the AI (retry up to 3 times)
    reply = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            detail = getattr(e, "body", None) or str(e)
            logger.error(f"AI error (attempt {attempt + 1}): {detail}")
            time.sleep(2)

    if reply is None:
        raise HTTPException(status_code=502, detail="The AI could not respond right now")

    # 4. Save both messages
    db.add(MessageDB(session_id=req.session_id, role="user", content=req.message))
    db.add(MessageDB(session_id=req.session_id, role="assistant", content=reply))
    db.commit()

    logger.info(f"Chat [{req.session_id}] success")
    return {"reply": reply}


@app.get("/chat/{session_id}", dependencies=[Depends(verify_api_key)])
def get_history(session_id: str, db: Session = Depends(get_db)):
    return (
        db.query(MessageDB)
        .filter(MessageDB.session_id == session_id)
        .order_by(MessageDB.id)
        .all()
    )