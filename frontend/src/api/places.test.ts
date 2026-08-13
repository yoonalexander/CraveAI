import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSuggestions, PlacesQuotaError } from "./places";

afterEach(() => {
    window.localStorage.clear();
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
});
