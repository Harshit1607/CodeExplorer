import os
import uuid
import shutil
from git import Repo, GitCommandError
from fastapi import HTTPException

BASE_DIR = "workspace"

def clone_repo(repo_url: str) -> str:
    # Basic validation
    if not repo_url.startswith("https://github.com/"):
        raise HTTPException(
            status_code=400,
            detail="Only public GitHub repositories are supported"
        )

    os.makedirs(BASE_DIR, exist_ok=True)

    repo_id = str(uuid.uuid4())
    repo_path = os.path.join(BASE_DIR, repo_id)

    try:
        Repo.clone_from(repo_url, repo_path, depth=1)
    except GitCommandError as e:
        # Cleanup partial clone
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path, ignore_errors=True)

        raise HTTPException(
            status_code=400,
            detail="Failed to clone repository. Check the URL and try again."
        )

    return repo_path
