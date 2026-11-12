import os
import shutil
import stat
import sys


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
