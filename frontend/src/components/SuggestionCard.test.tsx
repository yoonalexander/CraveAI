import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SuggestionCard } from "./SuggestionCard";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: null, loading: false }),
}));

vi.mock("../context/GoogleMapsContext", () => ({
  useGoogleMaps: () => mapsState,
}));

const { mapsState } = vi.hoisted(() => ({
  mapsState: { isLoaded: false, hasApiKey: false },
}));

beforeEach(() => {
  mapsState.isLoaded = false;
  mapsState.hasApiKey = false;
});

describe("SuggestionCard", () => {
  it("shows a branded photo fallback and preserves signed-out save behavior", () => {
    render(
      <SuggestionCard
        description="10 Main Street"
        distance="1.2 km"
        placeId="place-1"
        rating={4.6}
        tags={["Thai"]}
        title="Green Basil"
      />,
    );

    expect(screen.getByRole("img", { name: "No photo available for Green Basil" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to save" })).toHaveAttribute("href", "/login");
    expect(screen.getByLabelText("4.6 out of 5 stars")).toBeInTheDocument();
  });

  it("loads the first Google photo and displays its author attribution", async () => {
    mapsState.isLoaded = true;
    mapsState.hasApiKey = true;
    const getURI = vi.fn(() => "https://example.test/photo.jpg");
    class MockPlace {
      photos = [
        {
          getURI,
          googleMapsURI: "https://maps.google.com/photo",
          authorAttributions: [
            { displayName: "Photo Owner", uri: "https://maps.google.com/owner" },
          ],
        },
      ];

      async fetchFields(): Promise<void> {}
    }
    Object.defineProperty(globalThis, "google", {
      configurable: true,
      value: {
        maps: {
          importLibrary: vi.fn().mockResolvedValue({ Place: MockPlace }),
        },
      },
    });

    render(
      <SuggestionCard
        description="10 Main Street"
        placeId="google-place-1"
        title="Photo Cafe"
      />,
    );

    await waitFor(() => expect(screen.getByRole("img", { name: "Google Maps photo of Photo Cafe" })).toHaveAttribute("src", "https://example.test/photo.jpg"));
    expect(screen.getByRole("link", { name: "Photo: Photo Owner" })).toHaveAttribute(
      "href",
      "https://maps.google.com/owner",
    );
    expect(getURI).toHaveBeenCalledWith({ maxHeight: 280, maxWidth: 320 });
  });
});
