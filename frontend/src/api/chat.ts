import type { Suggestion } from "./places";
import { apiFetch } from "./client";
import type { ViewportBounds } from "../types/searchArea";

export type LocationHint = {
  lat: number;
  lng: number;
  city?: string;
  radius?: number;
  bounds?: ViewportBounds;
};

type ChatRequestPayload = {
  query: string;
  message: string;
  location: LocationHint;
  candidate_places: CandidatePlacePayload[];
};

type CandidatePlacePayload = Pick<
  Suggestion,
  | "place_id"
  | "name"
  | "rating"
  | "user_ratings_total"
  | "address"
  | "lat"
  | "lng"
  | "tags"
>;

export type ChatMessage = {
  role: string;
  content: string;
};

export type ChatRecommendation = {
  name: string;
  place_id?: string | null;
  rating?: number | null;
  address?: string | null;
  reason?: string | null;
  lat?: number | null;
  lng?: number | null;
  match_score?: number | null;
  confidence?: "high" | "medium" | "low" | null;
  matching_dishes?: string[];
  matched_preferences?: string[];
  unmatched_preferences?: string[];
  evidence?: Array<{
    type: string;
    label: string;
    source_url?: string | null;
  }>;
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
  intent?: Record<string, unknown> | null;
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

export class ChatTimeoutError extends Error {
  constructor() {
    super("The recommendation took too long. Please try again in a moment.");
    this.name = "ChatTimeoutError";
  }
}

const FALLBACK_LOCATION: LocationHint = {
  lat: 43.6532,
  lng: -79.3832,
  city: "Toronto",
  radius: 5000,
};

const CHAT_REQUEST_TIMEOUT_MS = 25000;

/**
 * Send a chat query to the backend chat endpoint.
 */
export async function sendChat(
  query: string,
  options: { location?: LocationHint; candidatePlaces?: Suggestion[] } = {},
): Promise<ChatResponse> {
  const { location, candidatePlaces = [] } = options;

  const locationPayload: LocationHint = location
    ? { ...FALLBACK_LOCATION, ...location }
    : FALLBACK_LOCATION;

  const payload: ChatRequestPayload = {
    query,
    message: query,
    location: locationPayload,
    candidate_places: candidatePlaces.slice(0, 20).map((place) => ({
      place_id: place.place_id,
      name: place.name,
      rating: place.rating,
      user_ratings_total: place.user_ratings_total,
      address: place.address,
      lat: place.lat,
      lng: place.lng,
      tags: place.tags ?? [],
    })),
  };

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    CHAT_REQUEST_TIMEOUT_MS,
  );
  let response: Response;
  try {
    response = await apiFetch(
      "/chat",
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
      { csrf: false },
    );
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ChatTimeoutError();
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
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
  const response = await apiFetch("/chat/status", {}, { csrf: false });

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
