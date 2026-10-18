/** Browser-local recent scan URL history (not persisted to the backend). */

export const URL_HISTORY_KEY = "findableai:url-history";
export const URL_HISTORY_MAX = 3;

export function readUrlHistory(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(URL_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((u): u is string => typeof u === "string" && u.trim().length > 0)
      .map((u) => u.trim())
      .slice(0, URL_HISTORY_MAX);
  } catch {
    return [];
  }
}

function writeUrlHistory(urls: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      URL_HISTORY_KEY,
      JSON.stringify(urls.slice(0, URL_HISTORY_MAX))
    );
  } catch {
    // Quota / private mode — ignore
  }
}

/** Prepend a URL; dedupe case-insensitively; keep at most URL_HISTORY_MAX. */
export function pushUrlHistory(url: string): string[] {
  const trimmed = url.trim();
  if (!trimmed) return readUrlHistory();
  const lower = trimmed.toLowerCase();
  const next = [
    trimmed,
    ...readUrlHistory().filter((u) => u.toLowerCase() !== lower),
  ].slice(0, URL_HISTORY_MAX);
  writeUrlHistory(next);
  return next;
}

export function removeUrlHistory(url: string): string[] {
  const lower = url.trim().toLowerCase();
  const next = readUrlHistory().filter((u) => u.toLowerCase() !== lower);
  writeUrlHistory(next);
  return next;
}

export function clearUrlHistory(): string[] {
  writeUrlHistory([]);
  return [];
}
