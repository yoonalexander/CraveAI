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
  import.meta.env.VITE_API_BASE_URL?.toString()?.trim() ||
  "http://127.0.0.1:8000";

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
