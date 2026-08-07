import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSuggestions, PlacesQuotaError } from "./places";

afterEach(() => {
    window.localStorage.clear();
});

describe("fetchSuggestions", () => {
    it("persists and reuses the signed anonymous identity", async () => {
        const fetchMock = vi
            .spyOn(globalThis, "fetch")
            .mockResolvedValueOnce(
                new Response("[]", {
                    status: 200,
                    headers: {
                        "Content-Type": "application/json",
                        "X-CraveAI-Anonymous-Token": "signed-browser-token",
                    },
                }),
            )
            .mockResolvedValueOnce(
                new Response("[]", {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                }),
            );

        await fetchSuggestions(43.65, -79.38);
        await fetchSuggestions(43.65, -79.38);

        const secondRequest = fetchMock.mock.calls[1][1] as RequestInit;
        expect(secondRequest.headers).toMatchObject({
            "X-CraveAI-Anonymous-Token": "signed-browser-token",
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
});
