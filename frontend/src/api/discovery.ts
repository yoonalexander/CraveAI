import { apiFetch } from "./client";
import type { Coordinates } from "../types/searchArea";

export type DiscoverySource = {
  url: string;
  publisher: string;
  published_at: string | null;
  observed_at: string;
  evidence: string;
};
export type NewsDiscovery = {
  place_id: string;
  name: string;
  city: string;
  address: string | null;
  label: "newly_opened" | "trending" | "recently_spotted";
  opening_date: string | null;
  publisher_count: number;
  sources: DiscoverySource[];
  expires_at: string;
};
export type DiscoveryNews = {
  items: NewsDiscovery[];
  region: string | null;
  coverage: string[];
  status: "ready" | "partial" | "pending" | "stale" | "unavailable" | "unsupported";
  checked_at: string | null;
  expires_at: string | null;
  refresh_due_at: string | null;
};

export async function fetchDiscoveryNews(area: Coordinates, signal: AbortSignal): Promise<DiscoveryNews> {
  const query = new URLSearchParams({ lat: String(area.lat), lng: String(area.lng) });
  const response = await apiFetch(`/discovery/signals?${query}`, { signal }, { csrf: false });
  if (!response.ok) throw new Error("Restaurant news could not be loaded.");
  return response.json() as Promise<DiscoveryNews>;
}
