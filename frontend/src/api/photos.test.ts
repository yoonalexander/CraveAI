import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPlacePhoto, PhotoLimitError } from "./photos";
afterEach(() => vi.unstubAllGlobals());
describe("photo API boundary", () => {
  it("sends only a Place ID and index with cookie credentials and no persistent cache", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ place_id: "cafe", index: 0, total: 0, photo: null })));
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    await fetchPlacePhoto("cafe", 0, controller.signal);
    expect(fetch).toHaveBeenCalledWith("/api/places/photo", expect.objectContaining({ credentials: "include", cache: "no-store", signal: controller.signal, body: JSON.stringify({ place_id: "cafe", index: 0 }) }));
  });
  it("rejects quota failures and mismatched venues", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response("", { status: 429 })).mockResolvedValueOnce(new Response(JSON.stringify({ place_id: "wrong", photo: { uri: "wrong-photo" } })));
    vi.stubGlobal("fetch", fetch);
    await expect(fetchPlacePhoto("cafe", 0, new AbortController().signal)).rejects.toBeInstanceOf(PhotoLimitError);
    await expect(fetchPlacePhoto("cafe", 0, new AbortController().signal)).rejects.toThrow("Photo venue did not match.");
  });
});
