import { afterEach, describe, expect, it, vi } from "vitest";

import type { Suggestion } from "./places";
import { ChatTimeoutError, sendChat, streamChat } from "./chat";

afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("sendChat", () => {
  it("sends at most twenty sanitized session candidates", async () => {
    const candidates: Suggestion[] = Array.from({ length: 22 }, (_, index) => ({
      place_id: `place-${index}`,
      name: `Place ${index}`,
      rating: 4.5,
      user_ratings_total: 100 + index,
      address: `${index} Test Street`,
      reason: "This display-only field must not be sent",
      lat: 43.65,
      lng: -79.38,
      tags: ["Pizza"],
    }));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          reply: "Try these.",
          messages: [],
          recommendations: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await sendChat("pizza", {
      location: { lat: 43.65, lng: -79.38 },
      candidatePlaces: candidates,
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(request.body));
    expect(body.candidate_places).toHaveLength(20);
    expect(body.candidate_places[0]).toEqual({
      place_id: "place-0",
      name: "Place 0",
      rating: 4.5,
      user_ratings_total: 100,
      address: "0 Test Street",
      lat: 43.65,
      lng: -79.38,
      tags: ["Pizza"],
    });
    expect(body.candidate_places[0]).not.toHaveProperty("reason");
  });

  it("uses the legacy JSON contract when the streaming route is not deployed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response('{"detail":"Not Found"}', { status: 404 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ reply: "Try the pizza place.", messages: [], recommendations: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ));

    await streamChat("pizza", {
      location: { lat: 43.65, lng: -79.38 },
      contextMessages: [{ role: "user", content: "something cheesy", place_ids: [] }],
      saveConversation: true,
      ageConfirmed: true,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/chat/stream");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/chat");
    const legacyBody = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body));
    expect(legacyBody).toMatchObject({ query: "pizza", message: "pizza" });
    expect(legacyBody).not.toHaveProperty("context_messages");
    expect(legacyBody).not.toHaveProperty("save_conversation");
    expect(legacyBody).not.toHaveProperty("age_confirmed");
  });

  it("surfaces a backend gateway timeout as a chat timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "chat_pipeline_timeout" } }), {
        status: 504,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(sendChat("pizza")).rejects.toBeInstanceOf(ChatTimeoutError);
  });

  it("sends an empty candidate list when the suggestion pool is unavailable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          reply: "Searching live.",
          messages: [],
          recommendations: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await sendChat("dinner");

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(request.body));
    expect(body.candidate_places).toEqual([]);
    expect(body.location).toEqual({
      lat: 43.6532,
      lng: -79.3832,
      city: "Toronto",
      radius: 5000,
    });
  });

  it("passes the confirmed viewport bounds to the recommendation pipeline", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ reply: "Inside the map.", messages: [], recommendations: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const bounds = { north: 43.75, south: 43.65, east: -79.34, west: -79.46 };

    await sendChat("ramen", {
      location: { lat: 43.7, lng: -79.4, radius: 7500, bounds },
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body)).location).toMatchObject({
      lat: 43.7,
      lng: -79.4,
      radius: 7500,
      bounds,
    });
  });
});
