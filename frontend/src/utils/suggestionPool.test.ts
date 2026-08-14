import { describe, expect, it } from "vitest";

import type { Suggestion } from "../api/places";
import {
  calculateDistanceKm,
  DEFAULT_ADVANCED_FILTERS,
  filterSuggestions,
  getNextSuggestionIndex,
  getVisibleSuggestions,
  groupSuggestionsForMap,
  mergeSuggestionsForBounds,
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

  it("requires explicit provider and dietary evidence for advanced filters", () => {
    const suggestions = makeSuggestions(3).map((suggestion, index) => ({
      ...suggestion,
      takeout: index === 0 ? true : index === 1 ? false : undefined,
      dietary_matches: index === 0 ? ["vegan", "halal"] : index === 1 ? ["vegan"] : undefined,
    }));
    const filtered = filterSuggestions(suggestions, new Set(), {
      ...DEFAULT_ADVANCED_FILTERS,
      takeout: true,
      dietary: ["vegan", "halal"],
    });
    expect(filtered).toEqual([suggestions[0]]);
  });

  it("keeps known in-bounds restaurants when a wider Google search returns a different subset", () => {
    const knownPlaza = makeSuggestions(16).map((place, index) => ({
      ...place,
      lat: 43.65 + index * 0.0001,
      lng: -79.38 + index * 0.0001,
    }));
    const broaderResults = makeSuggestions(8).map((place, index) => ({
      ...place,
      place_id: `broad-${index}`,
      lat: 43.66 + index * 0.001,
      lng: -79.39,
    }));

    const merged = mergeSuggestionsForBounds(knownPlaza, broaderResults, {
      north: 43.75,
      south: 43.6,
      east: -79.3,
      west: -79.5,
    });

    expect(merged).toHaveLength(20);
    expect(merged.slice(0, 16).map((place) => place.place_id)).toEqual(
      knownPlaza.map((place) => place.place_id),
    );
  });

  it("drops known restaurants outside a newly contracted viewport", () => {
    const places = makeSuggestions(3).map((place, index) => ({
      ...place,
      lat: 43.65 + index * 0.05,
    }));

    expect(mergeSuggestionsForBounds(places, [], {
      north: 43.66,
      south: 43.64,
      east: -79.37,
      west: -79.39,
    })).toEqual([places[0]]);
  });

  it("groups dense plaza restaurants at wide zoom and separates them when zoomed in", () => {
    const plaza = makeSuggestions(4).map((place, index) => ({
      ...place,
      lat: 43.65 + index * 0.0002,
      lng: -79.38 + index * 0.0002,
    }));

    expect(groupSuggestionsForMap(plaza, 13)).toHaveLength(1);
    expect(groupSuggestionsForMap(plaza, 13)[0].suggestions).toHaveLength(4);
    expect(groupSuggestionsForMap(plaza, 17)).toHaveLength(4);
  });
});
