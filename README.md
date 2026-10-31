# FastAPI AI Chatbot

A REST API chatbot built with FastAPI, PostgreSQL and the Groq API.
Chat history is stored in the database, so the bot remembers each conversation.

## Features
- User CRUD API with Pydantic validation
- API key authentication
- Webhook receiver
- AI chatbot with saved chat history
- Logging and error handling

## Tech Stack
FastAPI, PostgreSQL, SQLAlchemy, Pydantic, Groq API

## Setup
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your own keys
uvicorn chatbot:app --reload --reload-exclude "*.log"
```

## API
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /chat | Send a message |
| GET | /chat/{session_id} | Get chat history |