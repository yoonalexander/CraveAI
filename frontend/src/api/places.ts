import { apiFetch } from "./client";
import type { ViewportBounds } from "../types/searchArea";

export interface Suggestion {
  name: string;
  rating: number;
  address: string;
  reason: string;
  place_id: string;
  lat: number;
  lng: number;
  tags?: string[];
  user_ratings_total?: number;
  price_level?: number;
  open_now?: boolean;
}

export class PlacesQuotaError extends Error {
  resetAt: string | null;

  constructor(resetAt: string | null) {
    super("Today's nearby discovery limit has been reached.");
    this.name = "PlacesQuotaError";
    this.resetAt = resetAt;
  }
}

export async function fetchSuggestions(
    lat: number,
    lng: number,
    radius: number = 5000,
    signal?: AbortSignal,
    bounds?: ViewportBounds,
): Promise<Suggestion[]> {
  const search = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
    radius: String(radius),
  });
  if (bounds) {
    search.set("north", String(bounds.north));
    search.set("south", String(bounds.south));
    search.set("east", String(bounds.east));
    search.set("west", String(bounds.west));
  }
  const response = await apiFetch(
    `/places/suggestions?${search.toString()}`,
    { signal },
    { csrf: false },
  );
  if (!response.ok) {
    if (response.status === 429) {
      throw new PlacesQuotaError(response.headers.get("x-ratelimit-reset"));
    }
    throw new Error(`Failed to fetch suggestions (${response.status})`);
  }
  return response.json();
}
