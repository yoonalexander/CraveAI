import { Suggestion, FilterLabel } from "../api/places";
import type { ViewportBounds } from "../types/searchArea";

export const SUGGESTIONS_PER_ROTATION = 3;
export const MATERIAL_LOCATION_CHANGE_KM = 1;
export const SUGGESTION_POOL_LIMIT = 60;
export type SuggestionFilter = "budget" | "open";
export type AdvancedFilters = {
  cuisine: string;
  includeMenuLabels: boolean;
  minimumRating: number;
  maximumDistanceKm: number;
  priceLevels: number[];
  takeout: boolean;
  delivery: boolean;
  reservations: boolean;
  accessibility: boolean;
  dietary: string[];
  sort: "relevance" | "rating" | "distance" | "price";
};

export const DEFAULT_ADVANCED_FILTERS: AdvancedFilters = {
  cuisine: "",
  includeMenuLabels: true,
  minimumRating: 0,
  maximumDistanceKm: 20,
  priceLevels: [],
  takeout: false,
  delivery: false,
  reservations: false,
  accessibility: false,
  dietary: [],
  sort: "relevance",
};

export const CUISINE_OPTIONS = ["American", "Brazilian", "Chinese", "French", "Greek", "Indian", "Indonesian", "Italian", "Japanese", "Korean", "Lebanese", "Mediterranean", "Mexican", "Middle Eastern", "Spanish", "Thai", "Turkish", "Vietnamese"];

export function matchesDietaryLabels(labels: FilterLabel[] = [], requirements: string[], includeMenuLabels: boolean): boolean {
  if (!requirements.length) return true;
  const evidence = requirements.map((diet) => new Set(labels.filter((label) =>
    label.value === diet && (includeMenuLabels || label.source === "google")
  ).flatMap((label) => label.evidence.map((item) => item.id))));
  return [...evidence[0]].some((id) => evidence.every((items) => items.has(id)));
}

export function advancedFilterSummary(filters: AdvancedFilters): Array<{ key: keyof AdvancedFilters; label: string }> {
  const labels: Array<{ key: keyof AdvancedFilters; label: string }> = [];
  if (filters.cuisine) labels.push({ key: "cuisine", label: filters.cuisine });
  if (filters.minimumRating) labels.push({ key: "minimumRating", label: `${filters.minimumRating}+ stars` });
  if (filters.maximumDistanceKm < 20) labels.push({ key: "maximumDistanceKm", label: `Within ${filters.maximumDistanceKm} km` });
  if (filters.priceLevels.length) labels.push({ key: "priceLevels", label: filters.priceLevels.map((level) => level ? "$".repeat(level) : "Free").join(" / ") });
  for (const [key, label] of [["takeout", "Takeout"], ["delivery", "Delivery"], ["reservations", "Reservations"], ["accessibility", "Accessible entrance"]] as const) {
    if (filters[key]) labels.push({ key, label });
  }
  if (filters.dietary.length) labels.push({ key: "dietary", label: filters.dietary.join(" + ") });
  if (!filters.includeMenuLabels) labels.push({ key: "includeMenuLabels", label: "Google labels only" });
  if (filters.sort !== "relevance") labels.push({ key: "sort", label: `Sort: ${filters.sort}` });
  return labels;
}

export function filterSuggestions(
  suggestions: Suggestion[],
  filters: Set<SuggestionFilter>,
  advanced: AdvancedFilters = DEFAULT_ADVANCED_FILTERS,
  origin?: { lat: number; lng: number } | null,
): Suggestion[] {
  const filtered = suggestions.filter((suggestion) => {
    if (
      filters.has("budget") &&
      (suggestion.price_level !== 0 && suggestion.price_level !== 1)
    ) {
      return false;
    }
    if (filters.has("open") && suggestion.open_now !== true) return false;
    if (advanced.cuisine.trim() && !(suggestion.cuisine_labels || []).some((label) =>
      label.value.toLowerCase() === advanced.cuisine.trim().toLowerCase() && (advanced.includeMenuLabels || label.source === "google"))) return false;
    if (advanced.minimumRating && (typeof suggestion.rating !== "number" || suggestion.rating < advanced.minimumRating)) return false;
    if (advanced.priceLevels.length && (typeof suggestion.price_level !== "number" || !advanced.priceLevels.includes(suggestion.price_level))) return false;
    if (advanced.takeout && suggestion.takeout !== true) return false;
    if (advanced.delivery && suggestion.delivery !== true) return false;
    if (advanced.reservations && suggestion.reservable !== true) return false;
    if (advanced.accessibility && suggestion.wheelchair_accessible_entrance !== true) return false;
    if (!matchesDietaryLabels(suggestion.dietary_labels, advanced.dietary, advanced.includeMenuLabels)) return false;
    if (origin && advanced.maximumDistanceKm < 20 && calculateDistanceKm(origin.lat, origin.lng, suggestion.lat, suggestion.lng) > advanced.maximumDistanceKm) return false;
    return true;
  });
  if (advanced.sort === "rating") filtered.sort((a, b) => (b.rating || 0) - (a.rating || 0));
  if (advanced.sort === "distance" && origin) filtered.sort((a, b) => calculateDistanceKm(origin.lat, origin.lng, a.lat, a.lng) - calculateDistanceKm(origin.lat, origin.lng, b.lat, b.lng));
  if (advanced.sort === "price") filtered.sort((a, b) => (a.price_level ?? 99) - (b.price_level ?? 99));
  return filtered;
}

export function getVisibleSuggestions(
  suggestions: Suggestion[],
  startIndex: number,
): Suggestion[] {
  if (suggestions.length === 0) return [];

  const visibleCount = Math.min(SUGGESTIONS_PER_ROTATION, suggestions.length);
  return Array.from({ length: visibleCount }, (_, offset) => {
    return suggestions[(startIndex + offset) % suggestions.length];
  });
}

export function getNextSuggestionIndex(
  currentIndex: number,
  suggestionCount: number,
): number {
  if (suggestionCount === 0) return 0;
  return (currentIndex + SUGGESTIONS_PER_ROTATION) % suggestionCount;
}

export function calculateDistanceKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const earthRadiusKm = 6371;
  const latDelta = degreesToRadians(lat2 - lat1);
  const lngDelta = degreesToRadians(lng2 - lng1);
  const a =
    Math.sin(latDelta / 2) ** 2 +
    Math.cos(degreesToRadians(lat1)) *
      Math.cos(degreesToRadians(lat2)) *
      Math.sin(lngDelta / 2) ** 2;
  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function mergeSuggestionsForBounds(
  current: Suggestion[],
  incoming: Suggestion[],
  bounds?: ViewportBounds,
  limit: number = SUGGESTION_POOL_LIMIT,
): Suggestion[] {
  const incomingById = new Map(incoming.map((place) => [place.place_id, place]));
  const merged: Suggestion[] = [];
  const included = new Set<string>();

  // Fresh results take priority; old in-bounds places fill remaining capacity.
  incomingById.forEach((place) => {
    if (merged.length >= limit || (bounds && !isSuggestionInBounds(place, bounds))) return;
    merged.push(place);
    included.add(place.place_id);
  });
  if (!bounds) return merged;
  current.forEach((place) => {
    if (
      merged.length >= limit ||
      included.has(place.place_id) ||
      !isSuggestionInBounds(place, bounds)
    ) return;
    merged.push(place);
    included.add(place.place_id);
  });
  return merged.slice(0, limit);
}

function isSuggestionInBounds(
  suggestion: Suggestion,
  bounds: ViewportBounds,
): boolean {
  return (
    Number.isFinite(suggestion.lat) &&
    Number.isFinite(suggestion.lng) &&
    suggestion.lat >= bounds.south &&
    suggestion.lat <= bounds.north &&
    suggestion.lng >= bounds.west &&
    suggestion.lng <= bounds.east
  );
}

function degreesToRadians(degrees: number): number {
  return degrees * (Math.PI / 180);
}
