/**
 * Client auth headers for FindableAI API calls.
 *
 * Native EventSource cannot set Authorization / X-API-Key. Prefer fetch-based
 * streams (see useScanStream) so these headers are sent on every request,
 * including reconnects.
 *
 * Set NEXT_PUBLIC_FINDABLE_API_KEY only when the backend requires a key
 * (production / non-empty API_KEY). Leave unset for open local development.
 */
export function getAuthHeaders(): Record<string, string> {
  const key =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_FINDABLE_API_KEY?.trim()
      : undefined;
  if (!key) {
    return {};
  }
  return { "X-API-Key": key };
}
