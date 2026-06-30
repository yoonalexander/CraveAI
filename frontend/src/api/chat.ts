export type LocationHint = {
  lat: number;
  lng: number;
  city?: string;
  radius?: number;
};

type ChatRequestPayload = {
  query: string;
  message: string;
  user_id: string;
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
};

export type ChatResponse = {
  reply: string;
  messages: ChatMessage[];
  recommendations: ChatRecommendation[];
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
  "http://127.0.0.1:8000";

const DEMO_USER_ID_KEY = "craveai-demo-user-id";
let inMemoryDemoUserId: string | null = null;

export function getDemoUserId(): string {
  if (typeof window === "undefined") {
    return "demo-server";
  }

  try {
    const existing = window.localStorage.getItem(DEMO_USER_ID_KEY);
    if (existing) {
      return existing;
    }

    const generated =
      typeof window.crypto?.randomUUID === "function"
        ? window.crypto.randomUUID()
        : `demo-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(DEMO_USER_ID_KEY, generated);
    return generated;
  } catch {
    if (!inMemoryDemoUserId) {
      inMemoryDemoUserId =
        typeof window.crypto?.randomUUID === "function"
          ? window.crypto.randomUUID()
          : `demo-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    }
    return inMemoryDemoUserId;
  }
}

/**
 * Send a chat query to the backend chat endpoint.
 */
export async function sendChat(
  query: string,
  options: { userId?: string; location?: LocationHint } = {},
): Promise<ChatResponse> {
  const { userId = getDemoUserId(), location } = options;

  const locationPayload: LocationHint = location
    ? { ...FALLBACK_LOCATION, ...location }
    : FALLBACK_LOCATION;

  const payload: ChatRequestPayload = {
    query,
    message: query,
    user_id: userId,
    location: locationPayload,
  };

  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorPayload = await readErrorPayload(response);
    const quotaDetail = errorPayload.json?.detail;
    if (
      response.status === 429 &&
      quotaDetail?.code === "daily_token_quota_exceeded"
    ) {
      throw new ChatQuotaError(
        "You've reached today's CraveAI demo limit. Please try again after the daily reset.",
        quotaDetail.usage,
      );
    }

    const errorMessage = errorPayload.text || JSON.stringify(errorPayload.json);
    throw new Error(
      `Chat request failed with status ${response.status}: ${errorMessage}`,
    );
  }

  return response.json();
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
