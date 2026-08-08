import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Suggestion } from "./api/places";
import App from "./App";
import { fetchSuggestions, PlacesQuotaError } from "./api/places";

vi.mock("./api/places", async () => {
  const actual = await vi.importActual<typeof import("./api/places")>("./api/places");
  return { ...actual, fetchSuggestions: vi.fn() };
});

vi.mock("./components/ChatPanel", () => ({
  ChatPanel: ({ candidatePlaces }: { candidatePlaces: Suggestion[] }) => (
    <div data-testid="chat-pool-size">{candidatePlaces.length}</div>
  ),
}));
vi.mock("./components/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));
vi.mock("./components/ThemeToggle", () => ({
  ThemeToggle: () => <button type="button">Theme</button>,
}));
vi.mock("./components/AccountMenu", () => ({
  AccountMenu: () => <a href="/login">Sign in</a>,
}));
vi.mock("./components/SuggestionCard", () => ({
  SuggestionCard: ({ title }: { title: string }) => <div>{title}</div>,
}));

const mockedFetchSuggestions = vi.mocked(fetchSuggestions);
let locationSuccess: PositionCallback;

function makeSuggestions(count: number): Suggestion[] {
  return Array.from({ length: count }, (_, index) => ({
    place_id: `place-${index}`,
    name: `Place ${index}`,
    rating: 4.5,
    address: `${index} Test Street`,
    reason: "Test",
    lat: 43.65,
    lng: -79.38,
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
  mockedFetchSuggestions.mockReset();
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: vi.fn((success: PositionCallback) => {
        locationSuccess = success;
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

describe("App suggestion pool", () => {
  it("rotates three cards without making another request", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(10));
    render(<App />);
    await flushEffects();

    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Place 0")).toBeInTheDocument();
    expect(screen.getByTestId("chat-pool-size")).toHaveTextContent("10");

    act(() => vi.advanceTimersByTime(30_000));

    expect(screen.getByText("Place 3")).toBeInTheDocument();
    expect(screen.queryByText("Place 0")).not.toBeInTheDocument();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);
  });

  it("offers a manual retry and does not start an automatic retry loop", async () => {
    mockedFetchSuggestions
      .mockRejectedValueOnce(new Error("provider unavailable"))
      .mockResolvedValueOnce(makeSuggestions(4));
    render(<App />);
    await flushEffects();

    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(60_000));
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await flushEffects();

    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Place 0")).toBeInTheDocument();
  });

  it("waits through a backend cold start instead of aborting after 28 seconds", async () => {
    mockedFetchSuggestions.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve(makeSuggestions(4)), 60_000);
        }),
    );
    render(<App />);
    await flushEffects();

    act(() => vi.advanceTimersByTime(28_000));
    expect(
      screen.queryByText(/couldn't load suggestions in time/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/first load may take about a minute/i),
    ).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(32_000));
    await flushEffects();

    expect(screen.getByText("Place 0")).toBeInTheDocument();
    expect(
      screen.queryByText(/couldn't load suggestions in time/i),
    ).not.toBeInTheDocument();
  });

  it("shows the Places reset time and hides retry for quota errors", async () => {
    mockedFetchSuggestions.mockRejectedValue(
      new PlacesQuotaError("2026-08-08T00:00:00Z"),
    );
    render(<App />);
    await flushEffects();

    expect(
      screen.getByText(/nearby discovery limit has been reached/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Try again" }),
    ).not.toBeInTheDocument();
  });

  it("refetches only after a material location change", async () => {
    mockedFetchSuggestions.mockResolvedValue(makeSuggestions(4));
    render(<App />);
    await flushEffects();

    act(() => {
      locationSuccess({
        coords: {
          latitude: 43.654,
          longitude: -79.38,
        },
      } as GeolocationPosition);
    });
    await flushEffects();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(1);

    act(() => {
      locationSuccess({
        coords: {
          latitude: 43.67,
          longitude: -79.38,
        },
      } as GeolocationPosition);
    });
    await flushEffects();
    expect(mockedFetchSuggestions).toHaveBeenCalledTimes(2);
  });
});
