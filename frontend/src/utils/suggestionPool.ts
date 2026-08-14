import { Suggestion } from "../api/places";
import type { ViewportBounds } from "../types/searchArea";

export const SUGGESTIONS_PER_ROTATION = 3;
export const MATERIAL_LOCATION_CHANGE_KM = 1;
export const SUGGESTION_POOL_LIMIT = 20;
export type SuggestionFilter = "budget" | "open";

export type SuggestionMarkerGroup = {
  key: string;
  lat: number;
  lng: number;
  suggestions: Suggestion[];
};

export function filterSuggestions(
  suggestions: Suggestion[],
  filters: Set<SuggestionFilter>,
): Suggestion[] {
  return suggestions.filter((suggestion) => {
    if (
      filters.has("budget") &&
      (typeof suggestion.price_level !== "number" || suggestion.price_level > 1)
    ) {
      return false;
    }
    if (filters.has("open") && suggestion.open_now !== true) return false;
    return true;
  });
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
  if (!bounds) return incoming.slice(0, limit);

  const incomingById = new Map(incoming.map((place) => [place.place_id, place]));
  const merged: Suggestion[] = [];
  const included = new Set<string>();

  current.forEach((place) => {
    if (!isSuggestionInBounds(place, bounds) || included.has(place.place_id)) return;
    const refreshed = incomingById.get(place.place_id);
    merged.push(refreshed ? { ...place, ...refreshed } : place);
    included.add(place.place_id);
  });
  incoming.forEach((place) => {
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

export function groupSuggestionsForMap(
  suggestions: Suggestion[],
  zoom: number,
): SuggestionMarkerGroup[] {
  if (zoom >= 16) {
    return suggestions.map((place) => ({
      key: place.place_id,
      lat: place.lat,
      lng: place.lng,
      suggestions: [place],
    }));
  }

  const thresholdKm = Math.min(1.2, 0.12 * 2 ** (16 - zoom));
  const groups: SuggestionMarkerGroup[] = [];
  suggestions.forEach((place) => {
    if (!Number.isFinite(place.lat) || !Number.isFinite(place.lng)) return;
    const nearby = groups.find((group) =>
      calculateDistanceKm(group.lat, group.lng, place.lat, place.lng) <= thresholdKm,
    );
    if (!nearby) {
      groups.push({
        key: place.place_id,
        lat: place.lat,
        lng: place.lng,
        suggestions: [place],
      });
      return;
    }

    nearby.suggestions.push(place);
    const count = nearby.suggestions.length;
    nearby.lat = (nearby.lat * (count - 1) + place.lat) / count;
    nearby.lng = (nearby.lng * (count - 1) + place.lng) / count;
    nearby.key = nearby.suggestions.map((item) => item.place_id).sort().join(":");
  });
  return groups;
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
