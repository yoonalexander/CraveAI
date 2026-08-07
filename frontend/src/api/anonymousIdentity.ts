export const ANONYMOUS_TOKEN_HEADER = "X-CraveAI-Anonymous-Token";
const ANONYMOUS_TOKEN_STORAGE_KEY = "craveai-anonymous-token";

export function buildAnonymousHeaders(
  baseHeaders: Record<string, string> = {},
): Record<string, string> {
  const headers = { ...baseHeaders };
  const anonymousToken = readStoredAnonymousToken();
  if (anonymousToken) {
    headers[ANONYMOUS_TOKEN_HEADER] = anonymousToken;
  }
  return headers;
}

export function persistAnonymousToken(response: Response): void {
  const token = response.headers.get(ANONYMOUS_TOKEN_HEADER)?.trim();
  if (!token || !canUseLocalStorage()) {
    return;
  }
  window.localStorage.setItem(ANONYMOUS_TOKEN_STORAGE_KEY, token);
}

function readStoredAnonymousToken(): string | null {
  if (!canUseLocalStorage()) {
    return null;
  }
  const token = window.localStorage.getItem(ANONYMOUS_TOKEN_STORAGE_KEY);
  return token?.trim() || null;
}

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && Boolean(window.localStorage);
  } catch {
    return false;
  }
}
