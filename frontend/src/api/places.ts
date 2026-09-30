import { apiFetch } from "./client";
import type { ViewportBounds } from "../types/searchArea";

export interface Suggestion {
  name: string;
  rating: number | null;
  address: string;
  reason: string;
  place_id: string;
  lat: number;
  lng: number;
  tags?: string[];
  user_ratings_total?: number;
  price_level?: number | null;
  open_now?: boolean | null;
  takeout?: boolean | null;
  delivery?: boolean | null;
  reservable?: boolean | null;
  wheelchair_accessible_entrance?: boolean | null;
  dietary_matches?: string[];
  cuisine_labels?: FilterLabel[];
  dietary_labels?: FilterLabel[];
  enrichment_status?: "checked" | "unavailable";
  menu_status?: "assessed" | "no_evidence" | "not_checked" | "unavailable";
}

export type FilterLabel = {
  value: string;
  source: "google" | "inferred_menu";
  evidence: Array<{ id: string; label: string; source_url: string }>;
};
export type FilterData = Partial<Suggestion> & { place_id: string };

export async function fetchFilterData(placeIds: string[], signal?: AbortSignal): Promise<FilterData[]> {
  const response = await apiFetch("/places/filter-data", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ place_ids: [...new Set(placeIds)].slice(0, 10) }), signal,
  }, { csrf: false });
  if (response.status === 429) throw new PlacesQuotaError(response.headers.get("x-ratelimit-reset"));
  if (!response.ok) throw new Error("Restaurant details could not be checked.");
  return ((await response.json()) as { places: FilterData[] }).places;
}

export class PlacesQuotaError extends Error {
  resetAt: string | null;

  constructor(resetAt: string | null) {
    super("Today's nearby discovery limit has been reached.");
    this.name = "PlacesQuotaError";
    this.resetAt = resetAt;
  }
}

export type DiscoveryCoverage = {
  partialReason: string | null;
  resetAt: string | null;
};

export async function fetchSuggestions(
    lat: number,
    lng: number,
    radius: number = 5000,
    signal?: AbortSignal,
    bounds?: ViewportBounds,
    onCoverage?: (coverage: DiscoveryCoverage) => void,
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
  const places: Suggestion[] = await response.json();
  const coverage = response.headers.get("x-places-coverage");
  onCoverage?.({
    partialReason: coverage && coverage !== "complete" ? coverage : null,
    resetAt: response.headers.get("x-ratelimit-reset"),
  });
  return places;
}

export type DietaryEvidenceMatch = {
  place_id: string;
  dietary_matches: string[];
  evidence: Array<{ type: string; label: string; source_url: string }>;
};

export async function verifyDietaryEvidence(
  placeIds: string[], requirements: string[], signal?: AbortSignal,
): Promise<DietaryEvidenceMatch[]> {
  const response = await apiFetch("/places/dietary-evidence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ place_ids: placeIds.slice(0, 10), requirements: requirements.slice(0, 5) }),
    signal,
  }, { csrf: false });
  if (!response.ok) {
    if (response.status === 429) throw new PlacesQuotaError(response.headers.get("x-ratelimit-reset"));
    throw new Error(`Dietary evidence verification failed (${response.status})`);
  }
  return ((await response.json()) as { matches: DietaryEvidenceMatch[] }).matches;
}
