export type LocationHint = {
  lat: number;
  lng: number;
  city?: string;
  radius?: number;
};

type ChatRequestPayload = {
  query: string;
  message: string;
  location: LocationHint;
};

export type ChatMessage = {
  role: string;
  content: string;
};

export type ChatRecommendation = {
  name: string;
  rating?: number | null;
  address?: string | null;
  reason?: string | null;
  lat?: number | null;
  lng?: number | null;
};

export type UsageMetadata = {
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
  unlimited?: boolean;
};

export type ChatResponse = {
  reply: string;
  messages: ChatMessage[];
  recommendations: ChatRecommendation[];
  usage?: UsageMetadata | null;
};

export type ChatStatusResponse = {
  usage?: UsageMetadata | null;
};

type ApiErrorPayload = {
  detail?: {
    code?: string;
    message?: string;
    usage?: UsageMetadata;
  };
};

export class ChatQuotaError extends Error {
  usage?: UsageMetadata;

  constructor(message: string, usage?: UsageMetadata) {
    super(message);
    this.name = "ChatQuotaError";
    this.usage = usage;
  }
}

const FALLBACK_LOCATION: LocationHint = {
  lat: 43.2557,
  lng: -79.8711,
  city: "Hamilton",
  radius: 5000,
};

const API_URL =
  import.meta.env.VITE_API_URL?.toString()?.trim() ||
  import.meta.env.VITE_API_BASE_URL?.toString()?.trim() ||
  "http://127.0.0.1:8000";

const ANONYMOUS_TOKEN_HEADER = "X-CraveAI-Anonymous-Token";
const ANONYMOUS_TOKEN_STORAGE_KEY = "craveai-anonymous-token";
const DEV_BYPASS_HEADER = "X-CraveAI-Dev-Bypass";
const DEV_BYPASS_STORAGE_KEY = "craveai-dev-bypass-secret";

/**
 * Send a chat query to the backend chat endpoint.
 */
export async function sendChat(
  query: string,
  options: { location?: LocationHint } = {},
): Promise<ChatResponse> {
  const { location } = options;

  const locationPayload: LocationHint = location
    ? { ...FALLBACK_LOCATION, ...location }
    : FALLBACK_LOCATION;

  const payload: ChatRequestPayload = {
    query,
    message: query,
    location: locationPayload,
  };

  const headers: Record<string, string> = buildChatHeaders({
    "Content-Type": "application/json",
  });

  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  persistAnonymousToken(response);

  if (!response.ok) {
    const errorPayload = await readErrorPayload(response);
    const quotaDetail = errorPayload.json?.detail;
    if (
      response.status === 429 &&
      (quotaDetail?.code === "daily_chat_message_quota_exceeded" ||
        quotaDetail?.code === "daily_token_quota_exceeded")
    ) {
      throw new ChatQuotaError(
        "You've reached today's CraveAI chat limit. Please try again after the daily reset.",
        quotaDetail.usage ?? readUsageHeaders(response),
      );
    }

    const errorMessage = errorPayload.text || JSON.stringify(errorPayload.json);
    throw new Error(
      `Chat request failed with status ${response.status}: ${errorMessage}`,
    );
  }

  const body = (await response.json()) as ChatResponse;
  return {
    ...body,
    usage: body.usage ?? readUsageHeaders(response),
  };
}

export async function fetchChatStatus(): Promise<ChatStatusResponse> {
  const response = await fetch(`${API_URL}/chat/status`, {
    method: "GET",
    headers: buildChatHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Chat status request failed with status ${response.status}.`);
  }

  return (await response.json()) as ChatStatusResponse;
}

function readUsageHeaders(response: Response): UsageMetadata | null {
  const limit = readIntegerHeader(response, "x-ratelimit-limit");
  const remaining = readIntegerHeader(response, "x-ratelimit-remaining");
  const resetAt = response.headers.get("x-ratelimit-reset");

  if (limit === null || remaining === null || !resetAt) {
    return null;
  }

  return {
    limit,
    remaining,
    used: Math.max(limit - remaining, 0),
    reset_at: resetAt,
  };
}

function readIntegerHeader(response: Response, name: string): number | null {
  const value = response.headers.get(name);
  if (!value) {
    return null;
  }

  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function readStoredAnonymousToken(): string | null {
  if (!canUseLocalStorage()) {
    return null;
  }

  const token = window.localStorage.getItem(ANONYMOUS_TOKEN_STORAGE_KEY);
  return token?.trim() || null;
}

function buildChatHeaders(
  baseHeaders: Record<string, string> = {},
): Record<string, string> {
  const headers = { ...baseHeaders };
  const anonymousToken = readStoredAnonymousToken();
  if (anonymousToken) {
    headers[ANONYMOUS_TOKEN_HEADER] = anonymousToken;
  }
  const devBypassSecret = readStoredDevBypassSecret();
  if (devBypassSecret) {
    headers[DEV_BYPASS_HEADER] = devBypassSecret;
  }
  return headers;
}

function persistAnonymousToken(response: Response): void {
  const token = response.headers.get(ANONYMOUS_TOKEN_HEADER)?.trim();
  if (!token || !canUseLocalStorage()) {
    return;
  }

  window.localStorage.setItem(ANONYMOUS_TOKEN_STORAGE_KEY, token);
}

function readStoredDevBypassSecret(): string | null {
  if (!canUseLocalStorage()) {
    return null;
  }

  const secret = window.localStorage.getItem(DEV_BYPASS_STORAGE_KEY);
  return secret?.trim() || null;
}

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && Boolean(window.localStorage);
  } catch {
    return false;
  }
}

async function readErrorPayload(
  response: Response,
): Promise<{ json?: ApiErrorPayload; text?: string }> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return { json: (await response.json()) as ApiErrorPayload };
    } catch {
      return { text: "Unable to parse error response." };
    }
  }

  return { text: await response.text() };
}
