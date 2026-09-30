import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";

// Replace only the external Maps SDK. App, toolbar, filter logic, and the
// restaurant marker components all run normally.
vi.mock("@react-google-maps/api", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const sdkMap = { setCenter: vi.fn(), setZoom: vi.fn(), fitBounds: vi.fn() };
  const OverlayView = ({ children }: { children: React.ReactNode }) => <>{children}</>;
  OverlayView.OVERLAY_MOUSE_TARGET = "overlayMouseTarget";
  return {
    useJsApiLoader: () => ({ isLoaded: true, loadError: undefined }),
    GoogleMap: ({ children, onLoad, onUnmount }: {
      children: React.ReactNode; onLoad: (map: typeof sdkMap) => void; onUnmount: () => void;
    }) => {
      React.useEffect(() => { onLoad(sdkMap); return onUnmount; }, []);
      return <>{children}</>;
    },
    OverlayView,
    Marker: () => null,
    InfoWindow: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("keeps selected filters, counts, and actual restaurant markers in sync across repeated toggles and loading", async () => {
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "fake-test-key");
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
  const places = [
    { place_id: "cheap-open", name: "Cheap Open", price_level: 1, open_now: true },
    { place_id: "cheap-closed", name: "Cheap Closed", price_level: 1, open_now: false },
    { place_id: "costly-open", name: "Costly Open", price_level: 3, open_now: true },
    { place_id: "unknown", name: "Unknown Data" },
  ].map((place) => ({ ...place, rating: 4.2, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://test");
    let data: unknown = {};
    if (url.pathname === "/api/places/suggestions") { await pending; data = places; }
    if (url.pathname === "/api/chat/status") data = { usage: { limit: 3, used: 0, remaining: 3 } };
    if (url.hostname === "api.open-meteo.com") data = { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } };
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  }));
  render(<App />);
  await screen.findByText("Finding restaurants…");
  const open = screen.getByRole("button", { name: "Open Now" });
  const budget = screen.getByRole("button", { name: "Budget-friendly" });
  fireEvent.click(open);
  fireEvent.click(budget);
  fireEvent.click(budget);
  await act(async () => release());

  const markerNames = () => screen.queryAllByRole("button", { name: /^Show .+ on map$/ }).map((button) => button.getAttribute("aria-label"));
  await waitFor(() => expect(markerNames()).toEqual(["Show Cheap Open on map", "Show Costly Open on map"]));
  expect(open).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("2 of 4 loaded restaurants shown")).toBeInTheDocument();
  for (let i = 0; i < 12; i++) {
    fireEvent.click(open);
    expect(open).toHaveAttribute("aria-pressed", i % 2 ? "true" : "false");
    expect(markerNames()).toEqual(i % 2
      ? ["Show Cheap Open on map", "Show Costly Open on map"]
      : ["Show Cheap Open on map", "Show Cheap Closed on map", "Show Costly Open on map", "Show Unknown Data on map"]);
  }
  fireEvent.click(budget);
  expect(markerNames()).toEqual(["Show Cheap Open on map"]);
  expect(screen.getByText("1 of 4 loaded restaurants shown")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Filters" }));
  fireEvent.change(screen.getByLabelText("Minimum rating"), { target: { value: "4.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Show results" }));
  expect(markerNames()).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(open).toHaveAttribute("aria-pressed", "false");
  expect(budget).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByText("4 restaurants in this area")).toBeInTheDocument();
  expect(markerNames()).toEqual(["Show Cheap Open on map", "Show Cheap Closed on map", "Show Costly Open on map", "Show Unknown Data on map"]);
  fireEvent.click(budget);
  fireEvent.click(screen.getByRole("button", { name: "Filters" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "$$$" }));
  fireEvent.click(screen.getByRole("button", { name: "Show results" }));
  expect(budget).toHaveAttribute("aria-pressed", "false");
  expect(markerNames()).toEqual(["Show Costly Open on map"]);
  fireEvent.click(budget);
  expect(markerNames()).toEqual(["Show Cheap Open on map", "Show Cheap Closed on map"]);
  fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
  expect(screen.getByRole("checkbox", { name: "$$$" })).not.toBeChecked();
});

it("checks details on demand and keeps unknown service data excluded across map and Discovery", async () => {
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "fake-test-key");
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
  const places = ["Ramen Spot", "Unknown Spot"].map((name, index) => ({ name, place_id: `place-${index}`, rating: 4.2, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));
  let detailCalls = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://test");
    let data: unknown = {};
    if (url.pathname === "/api/places/suggestions") data = places;
    if (url.pathname === "/api/chat/status") data = { usage: { limit: 3, used: 0, remaining: 3 } };
    if (url.hostname === "api.open-meteo.com") data = { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } };
    if (url.pathname === "/api/places/filter-data") {
      detailCalls++;
      if (detailCalls === 1) return new Response("{}", { status: 503 });
      data = { places: [
        { place_id: "place-0", takeout: true, enrichment_status: "checked", cuisine_labels: [{ value: "Japanese", source: "google", evidence: [] }], menu_status: "assessed", dietary_labels: [{ value: "vegan", source: "inferred_menu", evidence: [{ id: "dish", label: "Vegan ramen", source_url: "https://restaurant.example/menu" }] }] },
        { place_id: "place-1", takeout: null, enrichment_status: "checked", menu_status: "no_evidence" },
      ] };
    }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  }));
  render(<App />);
  await screen.findByText("2 restaurants in this area");
  fireEvent.click(screen.getByRole("button", { name: "Filters" }));
  fireEvent.click(screen.getByLabelText(/^Takeout/));
  fireEvent.click(screen.getByLabelText("vegan"));
  fireEvent.click(screen.getByRole("button", { name: "Show results" }));
  const markers = () => screen.queryAllByRole("button", { name: /^Show .+ on map$/ });
  expect(markers()).toHaveLength(0);
  expect(detailCalls).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "Check next 2 restaurants" }));
  await screen.findByRole("alert");
  expect(markers()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Check next 2 restaurants" }));
  await screen.findByRole("button", { name: "Show Ramen Spot on map" });
  expect(markers()).toHaveLength(1);
  expect(screen.getByText("1 of 2 loaded restaurants shown")).toBeInTheDocument();
  const japanese = screen.getByRole("button", { name: "Japanese" });
  fireEvent.click(japanese);
  expect(japanese).toHaveAttribute("aria-pressed", "true");
  expect(markers()).toHaveLength(1);
  act(() => { for (let i = 0; i < 5; i++) japanese.click(); });
  expect(japanese).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "Any cuisine" })).toHaveAttribute("aria-pressed", "true");
  expect(markers()).toHaveLength(1); // Dietary and service filters survive cuisine changes.
  fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
  fireEvent.click(screen.getByLabelText("Include labels inferred from official menus"));
  fireEvent.click(screen.getByRole("button", { name: "Show results" }));
  expect(markers()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Remove Google labels only filter" }));
  expect(markers()).toHaveLength(1);
  fireEvent.click(screen.getByRole("link", { name: "Discovery" }));
  await screen.findByRole("heading", { name: "Ramen Spot" });
  expect(screen.queryByRole("heading", { name: "Unknown Spot" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Label sources"));
  expect(screen.getByRole("link", { name: "Vegan ramen" })).toHaveAttribute("href", "https://restaurant.example/menu");
  expect(screen.getByText("1 of 1 filtered restaurants in this collection")).toBeInTheDocument();
});
