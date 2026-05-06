from fastapi import APIRouter, HTTPException
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
    """
    # Log incoming request for debugging
    print(f"Chat request received. Question: {data.question[:50]}...")
    if data.analysis_data:
        print(f"Analysis data keys: {list(data.analysis_data.keys())}")
    else:
        print("WARNING: analysis_data is missing or None")
        raise HTTPException(
            status_code=400,
            detail="Repository analysis data is missing. Please wait for analysis to complete."
        )

    history = None
    if data.chat_history:
        history = [{"role": msg.role, "content": msg.content} for msg in data.chat_history]

    try:
        response = chat_about_repo(
            question=data.question,
            analysis_data=data.analysis_data,
            chat_history=history
        )
        return ChatResponse(response=response)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
