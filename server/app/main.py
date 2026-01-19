from dotenv import load_dotenv
load_dotenv()  # Load .env file for local development

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.analyze import router as analyze_router
from app.api.structure import router as structure_router
from app.api.chat import router as chat_router

app = FastAPI(title="CodeExplorer")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(analyze_router, prefix="/api")
app.include_router(structure_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
