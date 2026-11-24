/**
 * GitHub deep link to a file (and line range), or null when the repository is not on GitHub.
 * Rendered files (Markdown, reST) need `?plain=1` for the line anchor to work.
 */
export function sourceLink(repoMeta: any, file: string, start?: number | null, end?: number | null): string | null {
  const url: string | undefined = repoMeta?.url;
  if (!url || !url.startsWith('https://github.com/')) return null;
  const branch = repoMeta?.default_branch || 'HEAD';
  const lines = !start ? '' : end && end !== start ? `#L${start}-L${end}` : `#L${start}`;
  const plain = lines && /\.(md|mdx|markdown|rst)$/i.test(file) ? '?plain=1' : '';
  return `${url.replace(/\.git$/, '').replace(/\/$/, '')}/blob/${branch}/${file}${plain}${lines}`;
}
