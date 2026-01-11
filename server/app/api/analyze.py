from fastapi import APIRouter
from pydantic import BaseModel
from app.services.repo_ingestor import clone_repo
from app.services.repo_scanner import scan_repo
from app.services.code_analyzer import CodeAnalyzer

router = APIRouter()

class RepoRequest(BaseModel):
    repo_url: str

@router.post("/analyze")
def analyze_repo(data: RepoRequest):
    """
    Clone and fully analyze a GitHub repository.

    This endpoint:
    1. Clones the repository
    2. Scans file/folder structure
    3. Performs static code analysis
    4. Returns comprehensive analysis results
    """
    # Clone repository
    path = clone_repo(data.repo_url)

    # Basic scan
    scan_results = scan_repo(path)

    # Detailed code analysis
    analyzer = CodeAnalyzer(path)
    structure_analysis = analyzer.analyze()

    return {
        "message": "Repository cloned and analyzed successfully",
        "repository_url": data.repo_url,
        "path": path,
        "scan_results": scan_results,
        "structure_analysis": structure_analysis
    }
