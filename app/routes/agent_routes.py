"""
Agent routes — chat with your AI training coach.

POST /agent/chat  →  send a message with conversation history, get a coached response
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Tell me more about that ride",
                    "history": [
                        {"role": "user", "content": "How was my training this week?"},
                        {"role": "assistant", "content": "You did 3 rides totaling 120km..."},
                    ],
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with your AI training coach.
    Send conversation history for multi-turn context.
    """
    try:
        # Convert history to the format OpenAI expects
        history = [{"role": m.role, "content": m.content} for m in request.history]
        answer = await run_agent(request.message, conversation_history=history)
        return ChatResponse(response=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))