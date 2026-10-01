import type { ChatRecommendation } from "../api/chat";
import type { Suggestion } from "../api/places";
import type { Coordinates } from "../types/searchArea";

export type MapRestaurant = {
  key: string;
  place: (Suggestion | ChatRecommendation) & Coordinates;
  source: "nearby" | "chat";
  recommendationNumber?: number;
};

export function hasMapCoordinates(place: Suggestion | ChatRecommendation): place is (Suggestion | ChatRecommendation) & Coordinates {
  return typeof place.lat === "number" && Number.isFinite(place.lat) && Math.abs(place.lat) <= 90
    && typeof place.lng === "number" && Number.isFinite(place.lng) && Math.abs(place.lng) <= 180;
}

export function sameMapRestaurant(first: MapRestaurant["place"], second: MapRestaurant["place"]): boolean {
  if (first.place_id && second.place_id) return first.place_id === second.place_id;
  // An ID-less recommendation must identify the same name AND location.
  return first.name.trim().toLocaleLowerCase() === second.name.trim().toLocaleLowerCase()
    && Math.abs(first.lat - second.lat) <= 0.00001 && Math.abs(first.lng - second.lng) <= 0.00001;
}

export function getMapRestaurants(suggestions: Suggestion[], recommendations: ChatRecommendation[]): MapRestaurant[] {
  const result: MapRestaurant[] = [];
  function add(place: Suggestion | ChatRecommendation, source: MapRestaurant["source"], number?: number): void {
    if (!hasMapCoordinates(place)) return;
    const existing = result.find((entry) => sameMapRestaurant(entry.place, place));
    if (existing) {
      existing.recommendationNumber ??= number;
      // Nearby data remains authoritative; chat may fill missing public details.
      existing.place = { ...existing.place, place_id: existing.place.place_id || place.place_id,
        address: existing.place.address || place.address, rating: existing.place.rating ?? place.rating };
      return;
    }
    result.push({ key: place.place_id ? `id:${place.place_id}` : `location:${JSON.stringify([place.name.trim().toLocaleLowerCase(), place.lat, place.lng])}`,
      place, source, recommendationNumber: number });
  }
  suggestions.forEach((place) => add(place, "nearby"));
  recommendations.forEach((place, index) => add(place, "chat", index + 1));
  return result;
}
