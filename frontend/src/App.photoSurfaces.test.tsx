import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";

// Only the external Maps SDK and network are replaced. The four actual views,
// shared gallery, navigation, hydration and API client run together.
vi.mock("@react-google-maps/api", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const map = { setCenter: vi.fn(), setZoom: vi.fn(), fitBounds: vi.fn(), panTo: vi.fn() };
  const OverlayView = ({ children }: { children: React.ReactNode }) => <>{children}</>;
  OverlayView.OVERLAY_MOUSE_TARGET = "overlayMouseTarget";
  return {
    useJsApiLoader: () => ({ isLoaded: true, loadError: undefined }),
    GoogleMap: ({ children, onLoad, onUnmount }: { children: React.ReactNode; onLoad: (value: typeof map) => void; onUnmount: () => void }) => {
      React.useEffect(() => { onLoad(map); return onUnmount; }, []);
      return <>{children}</>;
    },
    OverlayView, Marker: () => null,
    InfoWindow: ({ children, onCloseClick }: { children: React.ReactNode; onCloseClick: () => void }) => <div role="dialog" aria-label="Restaurant information"><button onClick={onCloseClick}>Close restaurant</button>{children}</div>,
  };
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("uses the correct venue photos across map, chat, Discovery and Likes without persisting provider photos", async () => {
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "fake-map-key");
  window.history.replaceState({}, "", "/");
  window.localStorage.clear(); window.sessionStorage.clear();
  window.sessionStorage.setItem("craveai-age-18", "true");
  const places = ["Ramen House", "Thai Kitchen"].map((name, i) => ({ name, place_id: `place-${i}`, rating: 4.4, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));
  const photoCalls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://test");
    let data: unknown = {};
    if (url.pathname === "/api/auth/me") data = { user: { user_id: "user", email: "test@example.com", email_verified: true, username: "food_explorer" } };
    if (url.pathname === "/api/places/suggestions") data = places;
    if (url.pathname === "/api/places/resolve") data = { places };
    if (url.pathname === "/api/chat/status") data = { usage: { limit: 10, used: 0, remaining: 10 } };
    if (url.pathname === "/api/chat/stream") return new Response("", { status: 404 });
    if (url.pathname === "/api/chat") data = { reply: "Try the Thai kitchen.", recommendations: [places[1]], messages: [] };
    if (url.pathname === "/api/favorites/collections") data = { collections: [] };
    if (url.pathname === "/api/favorites/saved") data = { favorites: [
      { id: "saved", place_id: "place-0", collections: [], created_at: "today" },
      { id: "unresolved", place_id: "known-id", legacy_name: "Known saved venue", collections: [], created_at: "today" },
      { id: "legacy", legacy_name: "Legacy venue", collections: [], created_at: "today" },
    ] };
    if (url.hostname === "api.open-meteo.com") data = { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } };
    if (url.pathname === "/api/places/photo") {
      const { place_id, index } = JSON.parse(String(init?.body));
      photoCalls.push(place_id);
      data = { place_id, index, total: 2, photo: { uri: `https://lh3.googleusercontent.com/${place_id}-${index}`, source_uri: `https://maps.google.com/${place_id}/${index}`, report_uri: null, authors: [{ name: `${place_id} contributor`, uri: null, avatar_uri: null }] } };
    }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  }));
  render(<AuthProvider><App /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Show Ramen House on map" }));
  const popup = screen.getByRole("dialog", { name: "Restaurant information" });
  expect(await within(popup).findByAltText("Google Maps photo of Ramen House")).toHaveAttribute("src", "https://lh3.googleusercontent.com/place-0-0");
  fireEvent.click(within(popup).getByRole("button", { name: "Close restaurant" }));
  const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
  fireEvent.change(composer, { target: { value: "Thai dinner" } });
  fireEvent.keyDown(composer, { key: "Enter" });
  await screen.findByText("Try the Thai kitchen.");
  const chat = document.querySelector(".chat-recommendations") as HTMLElement;
  expect(await within(chat).findByAltText("Google Maps photo of Thai Kitchen")).toHaveAttribute("src", "https://lh3.googleusercontent.com/place-1-0");
  fireEvent.click(screen.getByRole("link", { name: "Discovery" }));
  const discovery = document.querySelector(".discovery-grid") as HTMLElement;
  expect(await within(discovery).findByAltText("Google Maps photo of Ramen House")).toHaveAttribute("src", "https://lh3.googleusercontent.com/place-0-0");
  fireEvent.click(screen.getByRole("link", { name: "Likes" }));
  expect(await screen.findByAltText("Google Maps photo of Ramen House")).toHaveAttribute("src", "https://lh3.googleusercontent.com/place-0-0");
  expect(await screen.findByAltText("Google Maps photo of Known saved venue")).toHaveAttribute("src", "https://lh3.googleusercontent.com/known-id-0");
  expect(screen.getByRole("img", { name: "No photo available for Legacy venue" })).toBeInTheDocument();
  expect(new Set(photoCalls)).toEqual(new Set(["place-0", "place-1", "known-id"]));
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("googleusercontent.com");
});
