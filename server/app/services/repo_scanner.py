import os

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv"
}

def scan_repo(repo_path: str):
    file_count = 0
    folders = set()
    files = []

    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for d in dirs:
            folders.add(d)

        for file in filenames:
            file_count += 1
            files.append(os.path.join(root, file))

    return {
        "file_count": file_count,
        "folder_count": len(folders),
        "sample_files": files[:20]
    }
