from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from app.services.chat_service import chat_about_repo

router = APIRouter()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    question: str
    analysis_data: dict
    chat_history: Optional[List[ChatMessage]] = None

class ChatResponse(BaseModel):
    response: str

@router.post("/chat", response_model=ChatResponse)
def chat(data: ChatRequest):
    """
    Chat about an analyzed repository.

    Send a question along with the analysis data to get AI-powered insights
    about the codebase.
    """
    history = None
    if data.chat_history:
        history = [{"role": msg.role, "content": msg.content} for msg in data.chat_history]

    response = chat_about_repo(
        question=data.question,
        analysis_data=data.analysis_data,
        chat_history=history
    )

    return ChatResponse(response=response)
