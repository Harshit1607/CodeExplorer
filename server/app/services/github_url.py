"""
GitHub repository URL normalization.

The client (`client/src/lib/githubUrl.ts`) applies the same rule, so anything the browser
accepts the server accepts too. Accepted forms, all normalized to `https://github.com/<owner>/<repo>`:

  https://github.com/owner/repo          http://github.com/owner/repo
  https://www.github.com/owner/repo      github.com/owner/repo
  https://github.com/owner/repo.git      https://github.com/owner/repo/
  https://github.com/owner/repo/tree/<ref>/<path>   (also /blob/...; the ref and path are dropped)
  ...plus any ?query or #fragment, which is dropped
"""
import re

INVALID_URL_MESSAGE = ("Please enter a valid GitHub repository URL "
                       "(e.g., https://github.com/user/repo)")

_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/(?:(?:tree|blob)/[^?#]*)?)?"
    r"(?:[?#].*)?$",
    re.IGNORECASE | re.ASCII,
)


def normalize_github_url(raw: str) -> str:
    """Return the canonical `https://github.com/<owner>/<repo>` URL, or raise ValueError."""
    m = _GITHUB_URL_RE.match((raw or "").strip())
    if not m or m.group("repo") in (".", ".."):
        raise ValueError(INVALID_URL_MESSAGE)
    return f"https://github.com/{m.group('owner')}/{m.group('repo')}"
