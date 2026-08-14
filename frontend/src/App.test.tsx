import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Suggestion } from "./api/places";
import App from "./App";
import { fetchSuggestions, PlacesQuotaError } from "./api/places";
import type { SearchArea } from "./types/searchArea";

vi.mock("./api/places", async () => {
  const actual = await vi.importActual<typeof import("./api/places")>("./api/places");
  return { ...actual, fetchSuggestions: vi.fn() };
});

let chatMount = 0;
vi.mock("./components/ChatPanel", () => ({
  ChatPanel: ({
    candidatePlaces,
    onConversationStart,
  }: {
    candidatePlaces: Suggestion[];
    onConversationStart?: () => void;
  }) => {
    const mount = ++chatMount;
    return (
      <div>
        <span data-testid="chat-pool-size">{candidatePlaces.length}</span>
        <span data-testid="chat-mount">{mount}</span>
        <button onClick={onConversationStart} type="button">Start conversation</button>
      </div>
    );
  },
}));

const viewportArea: SearchArea = {
  center: { lat: 43.7, lng: -79.4 },
  bounds: { north: 43.75, south: 43.65, east: -79.34, west: -79.46 },
  radius: 7_500,
  label: "Map area",
};

vi.mock("./components/MapView", () => ({
  MapView: ({ onSearchArea }: { onSearchArea: (area: SearchArea) => void }) => (
    <div data-testid="map">
      <button onClick={() => onSearchArea(viewportArea)} type="button">Search this area</button>
    </div>
  ),
}));
vi.mock("./components/Sidebar", () => ({
  Sidebar: ({ onNavigate }: { onNavigate: (path: string, reset?: boolean) => void }) => (
    <nav data-testid="sidebar">
      <button onClick={() => onNavigate("/", true)} type="button">New chat</button>
      <button onClick={() => onNavigate("/discovery")} type="button">Discovery</button>
    </nav>
  ),
}));
vi.mock("./api/weather", () => ({
  fetchCurrentWeather: vi.fn().mockResolvedValue({
    temperature: 20,
    condition: "Clear",
    isDay: true,
  }),
}));
vi.mock("./components/AccountMenu", () => ({
  AccountMenu: () => <a href="/login">Sign in</a>,
}));
vi.mock("./components/SuggestionCard", () => ({
  SuggestionCard: ({ title }: { title: string }) => <article>{title}</article>,
}));

const mockedFetchSuggestions = vi.mocked(fetchSuggestions);

function makeSuggestions(count: number): Suggestion[] {
  return Array.from({ length: count }, (_, index) => ({
    place_id: `place-${index}`,
    name: `Place ${index}`,
    rating: 4.5,
    address: `${index} Test Street`,
    reason: "Test",
    lat: 43.65 + index * 0.001,
    lng: -79.38,
    price_level: index % 2,
    open_now: index % 2 === 0,
  }));
}

async function flushEffects(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  window.history.replaceState({}, "", "/");
  mockedFetchSuggestions.mockReset();
  chatMount = 0;
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: vi.fn((success: PositionCallback) => {
        success({
          coords: {
            latitude: 43.65,
            longitude: -79.38,
            accuracy: 10,
            altitude: null,
            altitudeAccuracy: null,
            heading: null,
            speed: null,
            toJSON: () => ({}),
          },
          timestamp: Date.now(),
          toJSON: () => ({}),
        } as GeolocationPosition);
      }),
    },
  });
});

describe("Airbnb-style application shell", () => {
  it("renders placeholder routes and responds to browser history", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(4));
    window.history.replaceState({}, "", "/help");
    render(<App />);
    expect(screen.getByRole("heading", { name: "A CraveAI help centre is coming." })).toBeInTheDocument();

    act(() => {
      window.history.pushState({}, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.queryByRole("heading", { name: "A CraveAI help centre is coming." })).not.toBeInTheDocument();
  });

  it("keeps suggested cards off Home and shows the entire pool on Discovery", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(10));
    render(<App />);
    await flushEffects();

    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("10");
    expect(screen.queryByText("Place 0")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Today’s Suggested Spots" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Discovery" }));
    expect(screen.getByRole("heading", { name: "Today’s Suggested Spots" })).toBeInTheDocument();
    expect(screen.getByText("Place 0")).toBeInTheDocument();
    expect(screen.getByText("Place 9")).toBeInTheDocument();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);
  });

  it("does not spend a Places request until Search this area is confirmed", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(4));
    render(<App />);
    await flushEffects();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.pointerDown(screen.getByTestId("map"));
      await Promise.resolve();
    });
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    await flushEffects();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(2);
    expect(mockedFetchSuggestions.mock.calls[1][4]).toEqual(viewportArea.bounds);
  });

  it("preserves prior results when a viewport request fails and retries that viewport", async () => {
    mockedFetchSuggestions
      .mockResolvedValueOnce(makeSuggestions(4))
      .mockRejectedValueOnce(new Error("provider unavailable"))
      .mockResolvedValueOnce(makeSuggestions(6));
    render(<App />);
    await flushEffects();

    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    await flushEffects();
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("4");
    expect(screen.getByText(/previous results are still shown/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await flushEffects();
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("6");
    expect(mockedFetchSuggestions.mock.calls[2][4]).toEqual(viewportArea.bounds);
  });

  it("retains already discovered in-bounds restaurants when a wider search returns fewer places", async () => {
    const plaza = makeSuggestions(16);
    const broad = makeSuggestions(8).map((place, index) => ({
      ...place,
      place_id: `broad-${index}`,
      name: `Broad ${index}`,
    }));
    mockedFetchSuggestions
      .mockResolvedValueOnce(plaza)
      .mockResolvedValueOnce(broad);
    render(<App />);
    await flushEffects();
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("16");

    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    await flushEffects();

    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("20");
    fireEvent.click(screen.getByRole("button", { name: "Discovery" }));
    expect(screen.getByText("Place 0")).toBeInTheDocument();
    expect(screen.getByText("Place 15")).toBeInTheDocument();
  });

  it("allows the backend cold start without an early timeout", async () => {
    mockedFetchSuggestions.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(makeSuggestions(4)), 60_000)),
    );
    render(<App />);
    await flushEffects();

    act(() => vi.advanceTimersByTime(28_000));
    expect(screen.queryByText(/couldn't load this area in time/i)).not.toBeInTheDocument();
    expect(screen.getByText("Finding restaurants…")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(32_000));
    await flushEffects();
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("4");
  });

  it("shows quota feedback without offering a retry", async () => {
    mockedFetchSuggestions.mockRejectedValue(new PlacesQuotaError("2026-08-08T00:00:00Z"));
    render(<App />);
    await flushEffects();

    expect(screen.getByText(/nearby discovery limit has been reached/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("uses the same active filters for chat and Discovery", async () => {
    const places = makeSuggestions(3);
    places[1].price_level = 2;
    places[2].price_level = undefined;
    mockedFetchSuggestions.mockResolvedValue(places);
    render(<App />);
    await flushEffects();

    fireEvent.click(screen.getByRole("button", { name: /Under \$20/i }));
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("1");
    fireEvent.click(screen.getByRole("button", { name: "Discovery" }));
    expect(screen.getByText("Place 0")).toBeInTheDocument();
    expect(screen.queryByText("Place 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Place 2")).not.toBeInTheDocument();
  });

  it("New chat resets the conversation but retains the confirmed restaurant pool", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(5));
    render(<App />);
    await flushEffects();
    const firstMount = screen.getByTestId("chat-mount").textContent;

    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("5");
    expect(screen.getByTestId("chat-mount").textContent).not.toBe(firstMount);
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);
  });
});
