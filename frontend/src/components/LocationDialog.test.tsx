import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocationDialog } from "./LocationDialog";

vi.mock("../context/GoogleMapsContext", () => ({
  useGoogleMaps: () => ({ isLoaded: false, hasApiKey: false }),
}));

describe("LocationDialog", () => {
  it("uses a successful device location and returns its coordinates", () => {
    const select = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((success: PositionCallback) =>
          success({ coords: { latitude: 43.7, longitude: -79.4 } } as GeolocationPosition),
        ),
      },
    });

    render(<LocationDialog onClose={vi.fn()} onSelect={select} open />);
    fireEvent.click(screen.getByRole("button", { name: "Use my current location" }));

    expect(select).toHaveBeenCalledWith({
      lat: 43.7,
      lng: -79.4,
      label: "Current location",
      source: "device",
    });
  });

  it("closes on Escape and keeps manual search disabled without a browser key", () => {
    const close = vi.fn();
    render(<LocationDialog onClose={close} onSelect={vi.fn()} open />);
    expect(screen.getByRole("textbox", { name: "Search for a place" })).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});
