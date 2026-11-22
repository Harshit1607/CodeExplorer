/**
 * GitHub repository URL normalization. Same rule as the server
 * (server/app/services/github_url.py), so anything accepted here is accepted there.
 *
 * Accepts http/https or no scheme, an optional `www.`, a trailing `.git` or `/`,
 * `/tree/<ref>/<path>` or `/blob/...` browser links, and any ?query or #fragment.
 * Returns `https://github.com/<owner>/<repo>`, or null when the input is not a repo URL.
 */
const GITHUB_URL_RE =
  /^(?:https?:\/\/)?(?:www\.)?github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)\/([\w.-]+?)(?:\.git)?(?:\/(?:(?:tree|blob)\/[^?#]*)?)?(?:[?#].*)?$/i;

export function normalizeGithubUrl(raw: string): string | null {
  const m = GITHUB_URL_RE.exec((raw || '').trim());
  if (!m || m[2] === '.' || m[2] === '..') return null;
  return `https://github.com/${m[1]}/${m[2]}`;
}
