import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSuggestions, PlacesQuotaError } from "./places";

afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.useRealTimers();
});

describe("fetchSuggestions", () => {
    it("uses the same-origin API and includes opaque cookies", async () => {
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response("[]", {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );

        await fetchSuggestions(43.65, -79.38);

        expect(fetchMock.mock.calls[0][0]).toBe(
            "/api/places/suggestions?lat=43.65&lng=-79.38&radius=5000",
        );
        expect(fetchMock.mock.calls[0][1]).toMatchObject({
            credentials: "include",
        });
    });

    it("exposes the reset time from a Places quota response", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response(
                JSON.stringify({
                    detail: { code: "daily_places_request_quota_exceeded" },
                }),
                {
                    status: 429,
                    headers: {
                        "Content-Type": "application/json",
                        "X-RateLimit-Reset": "2026-08-08T00:00:00Z",
                    },
                },
            ),
        );

        await expect(fetchSuggestions(43.65, -79.38)).rejects.toEqual(
            expect.objectContaining<Partial<PlacesQuotaError>>({
                name: "PlacesQuotaError",
                resetAt: "2026-08-08T00:00:00Z",
            }),
        );
    });

    it("reports partial coverage while returning usable restaurants", async () => {
        const places = [{ place_id: "test", name: "Test Restaurant" }];
        vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(places), {
            status: 200,
            headers: { "Content-Type": "application/json", "X-Places-Coverage": "quota", "X-RateLimit-Reset": "2026-10-01T00:00:00Z" },
        }));
        const onCoverage = vi.fn();
        expect(await fetchSuggestions(43.65, -79.38, 5000, undefined, undefined, onCoverage)).toEqual(places);
        expect(onCoverage).toHaveBeenCalledWith({ partialReason: "quota", resetAt: "2026-10-01T00:00:00Z" });
    });

    it("sends a complete confirmed viewport without changing radial compatibility", async () => {
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response("[]", {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );

        await fetchSuggestions(43.7, -79.4, 7500, undefined, {
            north: 43.75,
            south: 43.65,
            east: -79.34,
            west: -79.46,
        });

        expect(fetchMock.mock.calls[0][0]).toBe(
            "/api/places/suggestions?lat=43.7&lng=-79.4&radius=7500&north=43.75&south=43.65&east=-79.34&west=-79.46",
        );
    });

    it("reuses a recent map area, preserves its coverage, and refreshes after expiry", async () => {
        vi.useFakeTimers();
        const places = [{ place_id: "osm:1", source: "openstreetmap", name: "Test Restaurant", lat: 43.65, lng: -79.38 }];
        const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(places, {
            headers: { "X-Places-Coverage": "catalog", "X-Places-Requests": "0" },
        }));
        const onCoverage = vi.fn();
        await fetchSuggestions(43.65, -79.38);
        expect(await fetchSuggestions(43.65, -79.38, 5000, undefined, undefined, onCoverage)).toEqual(places);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(onCoverage).toHaveBeenCalledWith({ partialReason: "catalog", resetAt: null });

        await fetchSuggestions(43.65, -79.38, 5000, undefined, undefined, undefined, { includeProvider: true });
        await fetchSuggestions(43.66, -79.38);
        expect(fetchMock).toHaveBeenCalledTimes(3);

        vi.setSystemTime(Date.now() + 10 * 60 * 1000);
        await fetchSuggestions(43.65, -79.38);
        expect(fetchMock).toHaveBeenCalledTimes(4);
    });

    it.each(["complete", "combined", "quota", "catalog"])("does not cache %s responses with Google results", async (coverage) => {
        const places = [{ place_id: "google-id", name: "Test Restaurant", lat: 43.65, lng: -79.38 }];
        const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(places, {
            headers: { "X-Places-Coverage": coverage, "X-Places-Requests": coverage === "catalog" ? "0" : "1" },
        }));
        await fetchSuggestions(43.65, -79.38);
        await fetchSuggestions(43.65, -79.38);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(window.sessionStorage.length).toBe(0);
    });
});
