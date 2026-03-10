"""
Agent routes — chat with your AI training coach.

POST /agent/chat  →  send a message, get a coached response
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "How was my training this week?"},
                {"message": "Should I rest today or can I do a long ride?"},
                {"message": "Compare my last 7 days vs the 7 days before that"},
            ]
        }
    }


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with your AI training coach.

    The agent will automatically pull your Strava data as needed
    to answer your question.
    """
    try:
        answer = await run_agent(request.message)
        return ChatResponse(response=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
