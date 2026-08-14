import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MapView } from "./MapView";

const mapHarness = vi.hoisted(() => ({
  center: { lat: 43.7, lng: -79.4 },
  bounds: { north: 43.75, south: 43.65, east: -79.34, west: -79.46 },
}));

vi.mock("../context/GoogleMapsContext", () => ({
  useGoogleMaps: () => ({ isLoaded: true, loadError: undefined, hasApiKey: true }),
}));

vi.mock("@react-google-maps/api", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const fakeMap = {
    fitBounds: vi.fn(),
    setCenter: vi.fn(),
    setZoom: vi.fn(),
    getZoom: () => 13,
    getCenter: () => ({ lat: () => mapHarness.center.lat, lng: () => mapHarness.center.lng }),
    getBounds: () => ({
      getNorthEast: () => ({ lat: () => mapHarness.bounds.north, lng: () => mapHarness.bounds.east }),
      getSouthWest: () => ({ lat: () => mapHarness.bounds.south, lng: () => mapHarness.bounds.west }),
    }),
  };
  const OverlayView = ({ children }: { children: React.ReactNode }) => <>{children}</>;
  OverlayView.OVERLAY_MOUSE_TARGET = "overlayMouseTarget";
  return {
    GoogleMap: (props: {
      children: React.ReactNode;
      onDragStart: () => void;
      onIdle: () => void;
      onLoad: (map: typeof fakeMap) => void;
      onUnmount: () => void;
    }) => {
      React.useEffect(() => {
        props.onLoad(fakeMap);
        return props.onUnmount;
      }, []);
      return (
        <div>
          <button onClick={() => { props.onDragStart(); props.onIdle(); }} type="button">Pan map</button>
          {props.children}
        </div>
      );
    },
    Marker: () => null,
    OverlayView,
  };
});

const area = {
  center: { lat: 43.7, lng: -79.4 },
  radius: 5_000,
  label: "Toronto, ON",
};

async function settleMapLoad(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 10));
  });
}

beforeEach(() => {
  mapHarness.center = { lat: 43.7, lng: -79.4 };
  mapHarness.bounds = { north: 43.75, south: 43.65, east: -79.34, west: -79.46 };
});

describe("MapView viewport confirmation", () => {
  it("waits for the explicit Search this area action after movement", async () => {
    const onSearchArea = vi.fn();
    render(
      <MapView
        confirmedArea={area}
        isLocating={false}
        isSearching={false}
        locationLabel="Toronto, ON"
        onSearchArea={onSearchArea}
        originIsDevice
        originLocation={area.center}
        recenterVersion={1}
        recommendations={[]}
        suggestions={[]}
      />,
    );
    await settleMapLoad();
    expect(screen.queryByRole("button", { name: "Search this area" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pan map" }));
    expect(onSearchArea).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));

    expect(onSearchArea).toHaveBeenCalledOnce();
    expect(onSearchArea.mock.calls[0][0]).toMatchObject({
      center: mapHarness.center,
      bounds: mapHarness.bounds,
      label: "Map area",
    });
  });

  it("blocks viewport requests wider than twenty kilometres", async () => {
    mapHarness.bounds = { north: 44.2, south: 43.2, east: -78.8, west: -80 };
    const onSearchArea = vi.fn();
    render(
      <MapView
        confirmedArea={area}
        isLocating={false}
        isSearching={false}
        locationLabel="Toronto, ON"
        onSearchArea={onSearchArea}
        originIsDevice={false}
        originLocation={area.center}
        recenterVersion={1}
        recommendations={[]}
        suggestions={[]}
      />,
    );
    await settleMapLoad();
    fireEvent.click(screen.getByRole("button", { name: "Pan map" }));

    const guard = screen.getByRole("button", { name: "Zoom in to search this area" });
    expect(guard).toBeDisabled();
    fireEvent.click(guard);
    expect(onSearchArea).not.toHaveBeenCalled();
  });
});
