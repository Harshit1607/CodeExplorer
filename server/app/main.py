from dotenv import load_dotenv
load_dotenv()  # Load .env file for local development

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.analyze import router as analyze_router
from app.api.structure import router as structure_router
from app.api.chat import router as chat_router
from app.api.search import router as search_router

app = FastAPI(title="CodeExplorer")

# Verify reload
print("\n" + "="*50)
print("  SERVER RELOADED - CORS FIX APPLIED")
print("="*50 + "\n")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, # Temporarily disable for maximum compatibility
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api")
app.include_router(structure_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")
