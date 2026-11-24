/**
 * `path:line` / `path:start-end` citations in AI-written text. Same pattern and key format as the
 * server (CITATION_RE and find_citations in server/app/services/report_grounding.py), so a key
 * found here can be looked up in the report's `grounding.citations`.
 */
const CITATION_RE =
  /(?<![\w/.:@+-])((?:\.\/)?[\w.@+-][\w.@+[\]-]*(?:\/[\w.@+[\]-]+)*):L?(\d+)(?:\s*[-\u2013]\s*L?(\d+))?(?![\w.]*\d)/g;

const EXTENSIONLESS = new Set([
  'dockerfile', 'makefile', 'gnumakefile', 'jenkinsfile', 'containerfile', 'readme',
  'contributing', 'procfile', 'gemfile', 'rakefile', 'vagrantfile',
]);

function looksLikeFile(path: string): boolean {
  const name = path.split('/').pop() || '';
  return path.includes('/') || /\.[A-Za-z]\w{0,9}$/.test(name) || EXTENSIONLESS.has(name.toLowerCase());
}

export type CitationPart =
  | { kind: 'text'; text: string }
  | { kind: 'citation'; text: string; key: string };

/** Split `text` into plain text and citations (`key` is the server's normalised form). */
export function splitCitations(text: string): CitationPart[] {
  const parts: CitationPart[] = [];
  let last = 0;
  for (const m of text.matchAll(CITATION_RE)) {
    let path = m[1];
    if (path.startsWith('./')) path = path.slice(2);
    if (!looksLikeFile(path)) continue;
    const key = m[3] ? `${path}:${m[2]}-${m[3]}` : `${path}:${m[2]}`;
    const at = m.index ?? 0;
    if (at > last) parts.push({ kind: 'text', text: text.slice(last, at) });
    parts.push({ kind: 'citation', text: m[0], key });
    last = at + m[0].length;
  }
  if (last < text.length) parts.push({ kind: 'text', text: text.slice(last) });
  return parts;
}

/** GitHub deep link to a line range, or null when the repository is not on GitHub. */
export function sourceLink(repoMeta: any, file: string, start: number, end: number): string | null {
  const url: string | undefined = repoMeta?.url;
  if (!url || !url.startsWith('https://github.com/')) return null;
  const branch = repoMeta?.default_branch || 'HEAD';
  const lines = end && end !== start ? `#L${start}-L${end}` : `#L${start}`;
  return `${url.replace(/\.git$/, '').replace(/\/$/, '')}/blob/${branch}/${file}${lines}`;
}
