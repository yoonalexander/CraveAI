export type LocationHint = {
  lat: number;
  lng: number;
  city?: string;
  radius?: number;
};

type ChatRequestPayload = {
  query: string;
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

export type ChatResponse = {
  reply: string;
  messages: ChatMessage[];
  recommendations: ChatRecommendation[];
};

const FALLBACK_LOCATION: LocationHint = {
  lat: 43.2557,
  lng: -79.8711,
  city: "Hamilton",
  radius: 5000,
};

/**
 * Send a chat query to the backend chat endpoint.
 */
export async function sendChat(
  query: string,
  options: { userId?: string; location?: LocationHint } = {},
): Promise<ChatResponse> {
  const { userId = "testuser", location } = options;
  const baseUrl =
    import.meta.env.VITE_API_BASE_URL?.toString()?.trim() ||
    "http://127.0.0.1:8000";

  const locationPayload: LocationHint = location
    ? { ...FALLBACK_LOCATION, ...location }
    : FALLBACK_LOCATION;

  const payload: ChatRequestPayload = {
    query,
    user_id: userId,
    location: locationPayload,
  };

  const response = await fetch(`${baseUrl}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorMessage = await response.text();
    throw new Error(
      `Chat request failed with status ${response.status}: ${errorMessage}`,
    );
  }

  return response.json();
}
