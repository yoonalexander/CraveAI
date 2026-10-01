import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewsDiscoveries } from "./NewsDiscoveries";
import type { DiscoveryNews } from "../api/discovery";

const area = { lat: 43.65, lng: -79.38 };
const now = new Date("2026-09-30T12:00:00Z");
function snapshot(): DiscoveryNews {
  return { status: "ready", region: "Toronto & GTA", coverage: ["Toronto & GTA"], checked_at: now.toISOString(),
    expires_at: "2026-10-01T12:00:00Z", refresh_due_at: "2026-09-30T18:00:00Z", items: [{
      place_id: "hearth", name: "Hearth Table", city: "Toronto", address: null, label: "newly_opened",
      opening_date: "2026-09-20", publisher_count: 1, expires_at: "2026-11-19T00:00:00Z",
      sources: [{ url: "https://cbc.ca/food/hearth", publisher: "cbc.ca", published_at: null,
        observed_at: "2026-09-29T12:00:00Z", evidence: "Hearth Table opened in Toronto on September 20, 2026" }],
    }] };
}
const response = (json: unknown, status = 200) => new Response(JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
let news: DiscoveryNews;
let requests: ReturnType<typeof vi.fn>;
async function settle(): Promise<void> { await act(async () => { await Promise.resolve(); await Promise.resolve(); }); }
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(now); news = snapshot();
  requests = vi.fn(async (url: string) => {
    if (url.startsWith("/api/discovery/signals")) return response(news);
    if (url === "/api/places/photo") return response({ place_id: "hearth", total: 0, photo: null });
    if (url === "/api/places/resolve") return response({ places: [{ place_id: "hearth", name: "Hearth Table", lat: 43.66, lng: -79.4, rating: null, address: "10 Main Street", reason: "News pick" }] });
    return response({});
  });
  vi.stubGlobal("fetch", requests);
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("source-backed discoveries", () => {
  it("shows source evidence and index dates, hydrates one Place ID, and permits repeat map focus", async () => {
    const onShowOnMap = vi.fn(); render(<NewsDiscoveries area={area} onShowOnMap={onShowOnMap} />); await settle();
    expect(screen.getByText("Newly opened")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "cbc.ca" })).toHaveAttribute("href", news.items[0].sources[0].url);
    expect(screen.getByText(/First indexed/)).toBeInTheDocument();
    expect(screen.queryByText(/Published/)).not.toBeInTheDocument();
    expect(screen.getByText(news.items[0].sources[0].evidence)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Google Maps" })).toHaveAttribute("href", expect.stringContaining("query_place_id=hearth"));
    fireEvent.click(screen.getByRole("button", { name: "Show on map Hearth Table" })); await settle();
    expect(onShowOnMap).toHaveBeenCalledWith(expect.objectContaining({ place_id: "hearth", lat: 43.66, lng: -79.4 }));
    const resolve = requests.mock.calls.find(([url]) => url === "/api/places/resolve");
    expect(JSON.parse(resolve![1].body)).toEqual({ place_ids: ["hearth"] });
    fireEvent.click(screen.getByRole("button", { name: "Show on map Hearth Table" })); await settle();
    expect(onShowOnMap).toHaveBeenCalledTimes(2);
    expect(requests.mock.calls.some(([url]) => url.includes("/chat"))).toBe(false);
  });

  it("hides expired labels before waiting for a replacement and aborts an outstanding map lookup", async () => {
    news.expires_at = new Date(now.getTime() + 2000).toISOString();
    const onShowOnMap = vi.fn(); render(<NewsDiscoveries area={area} onShowOnMap={onShowOnMap} />); await settle();
    let finish: (value: Response) => void = () => undefined;
    requests.mockImplementation(async (url: string) => url === "/api/places/resolve" ? new Promise<Response>((resolve) => { finish = resolve; }) : new Promise<Response>(() => undefined));
    fireEvent.click(screen.getByRole("button", { name: "Show on map Hearth Table" })); await settle();
    const resolveSignal = requests.mock.calls.find(([url]) => url === "/api/places/resolve")![1].signal;
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.queryByText("Newly opened")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking restaurant news");
    expect(resolveSignal.aborted).toBe(true);
    await act(async () => { finish(response({ places: [{ place_id: "hearth", lat: 43.66, lng: -79.4 }] })); });
    expect(onShowOnMap).not.toHaveBeenCalled();
  });

  it("ignores an old area response and aborts a previous map lookup when the area changes", async () => {
    let oldNews: (value: Response) => void = () => undefined;
    requests.mockImplementationOnce(() => new Promise<Response>((resolve) => { oldNews = resolve; }));
    const onShowOnMap = vi.fn();
    const { rerender } = render(<NewsDiscoveries area={area} onShowOnMap={onShowOnMap} />); await settle();
    const oldSignal = requests.mock.calls[0][1].signal;
    news = { ...snapshot(), status: "unsupported", region: null, items: [], expires_at: null };
    rerender(<NewsDiscoveries area={{ lat: 49.28, lng: -123.12 }} onShowOnMap={onShowOnMap} />); await settle();
    expect(oldSignal.aborted).toBe(true);
    await act(async () => oldNews(response(snapshot())));
    expect(screen.queryByText("Hearth Table")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("no regional news picks for this area");
    news = snapshot(); rerender(<NewsDiscoveries area={area} onShowOnMap={onShowOnMap} />); await settle();
    let oldPlace: (value: Response) => void = () => undefined;
    requests.mockImplementationOnce(() => new Promise<Response>((resolve) => { oldPlace = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Show on map Hearth Table" })); await settle();
    const placeSignal = requests.mock.calls.find(([url]) => url === "/api/places/resolve")![1].signal;
    rerender(<NewsDiscoveries area={null} onShowOnMap={onShowOnMap} />); await settle();
    await act(async () => oldPlace(response({ places: [{ place_id: "hearth", lat: 43.66, lng: -79.4 }] })));
    expect(placeSignal.aborted).toBe(true); expect(onShowOnMap).not.toHaveBeenCalled();
  });

  it.each(["stale", "unavailable", "pending", "unsupported"] as const)("never displays restaurant badges for a %s source snapshot", async (status) => {
    news.status = status; render(<NewsDiscoveries area={area} onShowOnMap={vi.fn()} />); await settle();
    expect(screen.queryByText("Newly opened")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("clears failed data, retries explicitly, and keeps source links when map details are unavailable", async () => {
    requests.mockImplementationOnce(async () => response({}, 503));
    render(<NewsDiscoveries area={area} onShowOnMap={vi.fn()} />); await settle();
    expect(screen.queryByText("Newly opened")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry news" })); await settle();
    requests.mockImplementationOnce(async () => response({ places: [] }));
    fireEvent.click(screen.getByRole("button", { name: "Show on map Hearth Table" })); await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("map details are unavailable");
    expect(screen.getByRole("link", { name: "cbc.ca" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Google Maps" })).toBeInTheDocument();
  });
});
