import { apiFetch } from "./client";
import type { ViewportBounds } from "../types/searchArea";

const CATALOG_PREFIXES = {
  "osm:": "openstreetmap",
  "toronto-licence:": "toronto",
  "mississauga-directory-2025:": "mississauga",
} as const;

export type CatalogSource = typeof CATALOG_PREFIXES[keyof typeof CATALOG_PREFIXES];

export const CATALOG_ATTRIBUTIONS: Record<CatalogSource, { name: string; url: string }> = {
  openstreetmap: { name: "© OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright" },
  toronto: { name: "City of Toronto business licences", url: "https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/" },
  mississauga: { name: "Mississauga Business Directory", url: "https://www.mississauga.ca/services-and-programs/business/employment-survey/" },
};

export function catalogSourceForId(placeId: string): CatalogSource | undefined {
  return Object.entries(CATALOG_PREFIXES).find(([prefix]) => placeId.startsWith(prefix))?.[1];
}

export interface Suggestion {
  name: string;
  rating: number | null;
  address: string;
  reason: string;
  place_id: string;
  source?: CatalogSource;
  website?: string | null;
  phone?: string | null;
  hours?: string | null;
  checked_on?: string | null;
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
  source: "google" | "inferred_menu" | CatalogSource;
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

const MAP_CACHE_KEY = "craveai-map-cache-v1";
const MAP_CACHE_TTL_MS = 10 * 60 * 1000;
// Bound the serialized cache to 256 KiB even at two bytes per code unit.
const MAP_CACHE_MAX_LENGTH = 128 * 1024;

type CachedMapArea = { query: string; expiresAt: number; places: Suggestion[] };

function readMapCache(): CachedMapArea[] {
  try {
    const stored = sessionStorage.getItem(MAP_CACHE_KEY);
    const entries: CachedMapArea[] = stored ? JSON.parse(stored) : [];
    return entries.filter((entry) => entry.expiresAt > Date.now());
  } catch {
    return [];
  }
}

function cacheMapArea(query: string, places: Suggestion[], entries: CachedMapArea[]) {
  const entry = { query, expiresAt: Date.now() + MAP_CACHE_TTL_MS, places };
  if (JSON.stringify([entry]).length > MAP_CACHE_MAX_LENGTH) return;
  const recent = [entry, ...entries.filter((item) => item.query !== query)];
  let serialized = JSON.stringify(recent);
  while (serialized.length > MAP_CACHE_MAX_LENGTH) {
    recent.pop();
    serialized = JSON.stringify(recent);
  }
  try {
    sessionStorage.setItem(MAP_CACHE_KEY, serialized);
  } catch {
    // Browser storage is optional. The live request still works.
  }
}

export async function fetchSuggestions(
    lat: number,
    lng: number,
    radius: number = 5000,
    signal?: AbortSignal,
    bounds?: ViewportBounds,
    onCoverage?: (coverage: DiscoveryCoverage) => void,
    options?: { name?: string; includeProvider?: boolean },
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
  if (options?.name) search.set("name", options.name);
  if (options?.includeProvider) search.set("include_provider", "true");
  const query = search.toString();
  const cacheable = !options?.name && !options?.includeProvider;
  signal?.throwIfAborted();
  const cached = cacheable ? readMapCache().find((entry) => entry.query === query) : undefined;
  if (cached) {
    onCoverage?.({ partialReason: "catalog", resetAt: null });
    return cached.places;
  }
  const response = await apiFetch(
    `/places/suggestions?${query}`,
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
  if (cacheable && !signal?.aborted && coverage === "catalog" &&
      response.headers.get("x-places-requests") === "0" && places.length > 0 &&
      places.every((place) => place.source && catalogSourceForId(place.place_id) === place.source)) {
    cacheMapArea(query, places, readMapCache());
  }
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
