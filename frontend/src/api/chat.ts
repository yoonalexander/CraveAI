type ChatRequestPayload = {
  query: string;
  user_id: string;
  location: {
    lat: number;
    lng: number;
    city: string;
    radius: number;
  };
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
};

export type ChatResponse = {
  reply: string;
  messages: ChatMessage[];
  recommendations: ChatRecommendation[];
};

/**
 * Send a chat query to the backend chat endpoint.
 */
export async function sendChat(
  query: string,
  userId = "testuser",
): Promise<ChatResponse> {
  const baseUrl =
    import.meta.env.VITE_API_BASE_URL?.toString()?.trim() ||
    "http://127.0.0.1:8000";

  const payload: ChatRequestPayload = {
    query,
    user_id: userId,
    location: {
      lat: 43.2557,
      lng: -79.8711,
      city: "Hamilton",
      radius: 5,
    },
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
