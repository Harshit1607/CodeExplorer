import os
import shutil
import stat
import sys
from typing import Optional, Union

PathLike = Union[str, os.PathLike]


def inside_repo(repo_root: PathLike, path: PathLike) -> bool:
    """
    True when `path` is a regular file that stays inside `repo_root` once every symlink is
    resolved. Cloned repositories are untrusted: a committed symlink such as
    `src/x.py -> /etc/passwd` or `-> /proc/self/environ` must never be read.
    """
    try:
        root = os.path.realpath(repo_root)
        real = os.path.realpath(os.path.join(repo_root, path))
        if os.path.commonpath([root, real]) != root:
            return False
        return os.path.isfile(real)
    except (OSError, ValueError):
        return False


def read_repo_text(repo_root: PathLike, *parts: PathLike) -> Optional[str]:
    """
    Read a repository file as text (UTF-8, undecodable bytes dropped), or None when it is
    missing, unreadable, or resolves outside `repo_root` (see `inside_repo`).
    `parts` are joined onto `repo_root`; an absolute part replaces it, as with os.path.join.
    """
    path = os.path.join(repo_root, *parts)
    if not inside_repo(repo_root, path):
        return None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def _make_writable_and_retry(func, path, _exc):
    # Git marks pack/object files read-only; on Windows that makes rmtree fail.
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def remove_tree(path: str) -> None:
    """shutil.rmtree that also removes read-only files (git objects on Windows)."""
    if not path or not os.path.exists(path):
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=_make_writable_and_retry)
