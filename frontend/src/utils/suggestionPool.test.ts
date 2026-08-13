import { describe, expect, it } from "vitest";

import type { Suggestion } from "../api/places";
import {
  calculateDistanceKm,
  filterSuggestions,
  getNextSuggestionIndex,
  getVisibleSuggestions,
} from "./suggestionPool";

function makeSuggestions(count: number): Suggestion[] {
  return Array.from({ length: count }, (_, index) => ({
    place_id: `place-${index}`,
    name: `Place ${index}`,
    rating: 4.5,
    address: `${index} Test Street`,
    reason: "Test suggestion",
    lat: 43.65,
    lng: -79.38,
  }));
}

describe("suggestion pool rotation", () => {
  it("advances by three and shows a completely new full batch", () => {
    const suggestions = makeSuggestions(10);
    const first = getVisibleSuggestions(suggestions, 0);
    const nextIndex = getNextSuggestionIndex(0, suggestions.length);
    const second = getVisibleSuggestions(suggestions, nextIndex);

    expect(first.map((place) => place.place_id)).toEqual([
      "place-0",
      "place-1",
      "place-2",
    ]);
    expect(second.map((place) => place.place_id)).toEqual([
      "place-3",
      "place-4",
      "place-5",
    ]);
  });

  it.each([1, 2, 3, 4, 10, 20])(
    "shows every member of a %i-place pool before starting another cycle",
    (count) => {
      const suggestions = makeSuggestions(count);
      const seen = new Set<string>();
      let index = 0;

      while (seen.size < count) {
        for (const suggestion of getVisibleSuggestions(suggestions, index)) {
          seen.add(suggestion.place_id);
          if (seen.size === count) break;
        }
        index = getNextSuggestionIndex(index, suggestions.length);
      }

      expect(seen.size).toBe(count);
    },
  );

  it("distinguishes sub-kilometre movement from a material location change", () => {
    expect(calculateDistanceKm(43.65, -79.38, 43.654, -79.38)).toBeLessThan(1);
    expect(calculateDistanceKm(43.65, -79.38, 43.67, -79.38)).toBeGreaterThan(1);
  });

  it("filters budget and open places without treating missing metadata as a match", () => {
    const suggestions = makeSuggestions(4).map((suggestion, index) => ({
      ...suggestion,
      price_level: index === 0 ? 1 : index === 1 ? 2 : undefined,
      open_now: index < 2 ? true : index === 2 ? false : undefined,
    }));

    expect(filterSuggestions(suggestions, new Set(["budget"]))).toEqual([
      suggestions[0],
    ]);
    expect(filterSuggestions(suggestions, new Set(["open"]))).toEqual([
      suggestions[0],
      suggestions[1],
    ]);
    expect(filterSuggestions(suggestions, new Set(["budget", "open"]))).toEqual([
      suggestions[0],
    ]);
  });
});
