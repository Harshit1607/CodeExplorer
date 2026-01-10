from fastapi import APIRouter
from pydantic import BaseModel
from app.services.repo_ingestor import clone_repo
from app.services.repo_scanner import scan_repo

router = APIRouter()

class RepoRequest(BaseModel):
    repo_url: str

@router.post("/analyze")
def analyze_repo(data: RepoRequest):
    path = clone_repo(data.repo_url)
    scan_results = scan_repo(path)
    return {
        "message": "Repository cloned and scanned successfully",
        "path": path,
        "scan_results": scan_results
    }
