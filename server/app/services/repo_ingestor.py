import os
import re
import uuid
import shutil
from git import Repo, GitCommandError
from fastapi import HTTPException

BASE_DIR = "workspace"

def clone_repo(repo_url: str) -> str:
    # Trim whitespace
    repo_url = repo_url.strip()

    # Check if URL is empty
    if not repo_url:
        raise HTTPException(
            status_code=400,
            detail="Please enter a repository URL"
        )

    # Check if it's a GitHub URL
    if not repo_url.startswith("https://github.com/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Please enter a valid GitHub repository URL (e.g., https://github.com/username/repo)"
        )

    # Validate GitHub URL format (should have username and repo name)
    github_pattern = r'^https://github\.com/[\w.-]+/[\w.-]+/?$'
    if not re.match(github_pattern, repo_url.rstrip('.git')):
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub URL format. Expected: https://github.com/username/repository"
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

        error_msg = str(e).lower()

        # Check for common error patterns
        if "repository not found" in error_msg or "404" in error_msg:
            raise HTTPException(
                status_code=400,
                detail="Repository not found. Please check if the URL is correct and the repository exists."
            )
        elif "could not read from remote" in error_msg or "authentication" in error_msg:
            raise HTTPException(
                status_code=400,
                detail="Cannot access repository. This might be a private repository. Only public repositories are supported."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to clone repository. Please check the URL and ensure the repository is public."
            )

    return repo_path
