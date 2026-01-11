from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from app.services.code_analyzer import CodeAnalyzer

router = APIRouter()

class StructureRequest(BaseModel):
    repo_path: str

@router.post("/structure")
def get_repository_structure(data: StructureRequest):
    """
    Analyze repository structure and return detailed metadata.

    This endpoint performs static code analysis to extract:
    - File and folder structure
    - Language breakdown
    - Entry points
    - Key files
    - Functions, classes, and imports for each file
    """
    repo_path = data.repo_path

    # Validate path exists
    if not Path(repo_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository path not found: {repo_path}"
        )

    # Perform analysis
    analyzer = CodeAnalyzer(repo_path)
    structure = analyzer.analyze()

    return {
        "status": "success",
        "repository": repo_path,
        "analysis": structure
    }

@router.get("/structure/{repo_id}")
def get_structure_by_id(repo_id: str):
    """
    Get repository structure by repository ID (from workspace).
    """
    repo_path = f"workspace/{repo_id}"

    if not Path(repo_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository not found: {repo_id}"
        )

    # Perform analysis
    analyzer = CodeAnalyzer(repo_path)
    structure = analyzer.analyze()

    return {
        "status": "success",
        "repository_id": repo_id,
        "analysis": structure
    }
