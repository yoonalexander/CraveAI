import { Suggestion } from "../api/places";

export const SUGGESTIONS_PER_ROTATION = 3;
export const MATERIAL_LOCATION_CHANGE_KM = 1;
export type SuggestionFilter = "budget" | "open";

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

function degreesToRadians(degrees: number): number {
  return degrees * (Math.PI / 180);
}
