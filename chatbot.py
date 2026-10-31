import os
import time
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from openai import OpenAI

from databasetwo import SessionLocal, MessageDB
from logging.handlers import RotatingFileHandler

# Load variables from the .env file
load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
    RotatingFileHandler("chatbot.log", maxBytes=1_000_000, backupCount=3),
    logging.StreamHandler(),
],
)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")

app = FastAPI()

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1",
)
MODEL = "openai/gpt-oss-20b"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


@app.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. Load previous messages of this session
    old = (
        db.query(MessageDB)
        .filter(MessageDB.session_id == req.session_id)
        .order_by(MessageDB.id)
        .all()
    )

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

    # 4. Save both messages to the database
    db.add(MessageDB(session_id=req.session_id, role="user", content=req.message))
    db.add(MessageDB(session_id=req.session_id, role="assistant", content=reply))
    db.commit()

    logger.info(f"Chat [{req.session_id}] success")
    return {"reply": reply}


@app.get("/chat/{session_id}")
def get_history(session_id: str, db: Session = Depends(get_db)):
    return (
        db.query(MessageDB)
        .filter(MessageDB.session_id == session_id)
        .order_by(MessageDB.id)
        .all()
    )