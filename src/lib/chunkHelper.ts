export function chunk_text_browser(
  text: string,
  chunkSize: number = 900,
  chunkOverlap: number = 120
): string[] {
  const cleaned = (text || '').replace(/\r\n?/g, '\n').trim();
  if (!cleaned) return [];
  const paragraphs = cleaned
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  const chunks: string[] = [];
  let current = '';
  for (const para of paragraphs) {
    const candidate = current ? `${current}\n\n${para}` : para;
    if (candidate.length <= chunkSize) {
      current = candidate;
    } else {
      if (current) chunks.push(current);
      current = para.slice(0, chunkSize);
    }
  }
  if (current) chunks.push(current);
  return chunks;
}
