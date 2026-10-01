import { describe, expect, it } from "vitest";
import type { Suggestion } from "../api/places";
import { getMapRestaurants } from "./mapRestaurants";

const nearby: Suggestion = { place_id: "inside", name: "Same Brand", lat: 43.7, lng: -79.4, address: "1 Main Street", rating: 4.4, reason: "Nearby" };
describe("the shared map/list restaurant set", () => {
  it("deduplicates IDs and ID-less same-location picks while preserving original chat numbers and nearby data", () => {
    const entries = getMapRestaurants([nearby, { ...nearby }], [
      { name: "No coordinates" }, { ...nearby, address: "Old address", rating: 1 },
      { name: " SAME BRAND ", lat: nearby.lat, lng: nearby.lng },
      { name: "Outside", place_id: "outside", lat: 43.9, lng: -79.3 },
      { name: "Outside", place_id: "outside", lat: 43.9, lng: -79.3 },
    ]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({ source: "nearby", recommendationNumber: 2, place: { rating: 4.4, address: "1 Main Street" } });
    expect(entries[1]).toMatchObject({ source: "chat", recommendationNumber: 4 });
    expect(nearby.rating).toBe(4.4);
  });
  it("keeps distinct branches, even with the same name, and never pins malformed coordinates", () => {
    const entries = getMapRestaurants([nearby, { ...nearby, place_id: "other-branch", lat: 43.8 }], [
      { name: "Same Brand", lat: 43.9, lng: -79.4 }, { name: "Same Brand", lat: 43.9, lng: -79.4 },
      { name: "Missing", lat: null, lng: -79.4 }, { name: "Invalid", lat: NaN, lng: -79.4 },
      { name: "Out of range", lat: 91, lng: -79.4 }, { name: "Infinity", lat: 43.7, lng: Infinity },
    ]);
    expect(entries).toHaveLength(3);
    expect(new Set(entries.map((entry) => entry.key)).size).toBe(3);
  });
  it("lets an identified recommendation supply missing data without inventing an ID", () => {
    const entries = getMapRestaurants([], [{ name: "Venue", lat: 43.7, lng: -79.4 },
      { name: "Venue", place_id: "venue", rating: 4.2, address: "2 Main Street", lat: 43.7, lng: -79.4 }]);
    expect(entries).toHaveLength(1);
    expect(entries[0].place).toMatchObject({ place_id: "venue", rating: 4.2 });
  });
});
