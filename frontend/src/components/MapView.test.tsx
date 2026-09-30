import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MapView } from "./MapView";

const mapHarness = vi.hoisted(() => ({
  center: { lat: 43.7, lng: -79.4 },
  bounds: { north: 43.75, south: 43.65, east: -79.34, west: -79.46 },
  panTo: vi.fn(),
  setZoom: vi.fn(),
}));

vi.mock("../context/GoogleMapsContext", () => ({
  useGoogleMaps: () => ({ isLoaded: true, loadError: undefined, hasApiKey: true }),
}));

vi.mock("@react-google-maps/api", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const fakeMap = {
    fitBounds: vi.fn(),
    setCenter: vi.fn(),
    setZoom: mapHarness.setZoom,
    panTo: mapHarness.panTo,
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
    InfoWindow: ({ children, onCloseClick }: { children: React.ReactNode; onCloseClick: () => void }) => (
      <div role="dialog"><button onClick={onCloseClick} type="button">Close restaurant</button>{children}</div>
    ),
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
  mapHarness.panTo.mockClear();
  mapHarness.setZoom.mockClear();
});

describe("MapView viewport confirmation", () => {
  it("renders every nearby pin and opens restaurant information on click", async () => {
    const suggestions = [0, 1, 2].map((index) => ({
      place_id: `place-${index}`, name: `Restaurant ${index}`, rating: 4.3,
      address: `${index} Main Street`, reason: "Nearby", lat: 43.7 + index * 0.0001, lng: -79.4,
    }));
    render(<MapView confirmedArea={area} isLocating={false} isSearching={false} locationLabel="Toronto"
      onSearchArea={vi.fn()} originIsDevice originLocation={area.center} recenterVersion={1}
      recommendations={[]} suggestions={suggestions} />);
    await settleMapLoad();
    expect(screen.getAllByRole("button", { name: /Show Restaurant/ })).toHaveLength(3);
    expect(screen.queryByText(/spots/)).not.toBeInTheDocument();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Show Restaurant 1 on map" }));
    fireEvent.click(screen.getByRole("button", { name: "Show Restaurant 1 on map" }));
    expect(mapHarness.panTo).toHaveBeenCalledWith({ lat: suggestions[1].lat, lng: suggestions[1].lng });
    expect(screen.getByRole("dialog")).toHaveTextContent("Restaurant 1");
    expect(screen.getByRole("dialog")).toHaveTextContent("1 Main Street");
    expect(screen.getByRole("link", { name: "Open in Google Maps" })).toHaveAttribute("href", expect.stringContaining("query_place_id=place-1"));
    expect(screen.queryByRole("button", { name: "Search this area" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close restaurant" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders sixty restaurant pins and does not search when the map is moved", async () => {
    const suggestions = Array.from({ length: 60 }, (_, index) => ({
      place_id: `place-${index}`, name: `Restaurant ${index}`, rating: index % 2 ? null : 3.6,
      address: `${index} Main Street`, reason: "Nearby", lat: 43.7 + index * 0.0001, lng: -79.4,
    }));
    const onSearchArea = vi.fn();
    render(<MapView confirmedArea={area} isLocating={false} isSearching={false} locationLabel="Toronto"
      onSearchArea={onSearchArea} originIsDevice originLocation={area.center} recenterVersion={1}
      recommendations={[]} suggestions={suggestions} />);
    await settleMapLoad();
    expect(screen.getAllByRole("button", { name: /Show Restaurant/ })).toHaveLength(60);
    fireEvent.click(screen.getByRole("button", { name: "Pan map" }));
    expect(onSearchArea).not.toHaveBeenCalled();
  });

  it("focuses chat-only places repeatedly and keeps the original recommendation number", async () => {
    const inside = { place_id: "inside", name: "Inside", rating: 4.5, address: "1 Main Street", reason: "Nearby", lat: 43.7, lng: -79.4 };
    const places = [
      inside,
      { place_id: "outside", name: "Outside", lat: 43.71, lng: -79.41 },
    ];
    const props = { confirmedArea: area, isLocating: false, isSearching: false, locationLabel: "Toronto",
      onSearchArea: vi.fn(), originIsDevice: true, originLocation: area.center, recenterVersion: 1,
      recommendations: places, suggestions: [inside] };
    const { rerender } = render(<MapView {...props} focusRequest={{ requestId: 1, place: places[1] }} />);
    await settleMapLoad();
    expect(screen.getByRole("button", { name: "Show Outside on map" })).toHaveTextContent("2");
    expect(screen.getByRole("dialog")).toHaveTextContent("Outside");
    expect(mapHarness.panTo).toHaveBeenCalledWith({ lat: 43.71, lng: -79.41 });
    expect(mapHarness.setZoom).toHaveBeenLastCalledWith(16);
    mapHarness.panTo.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Close restaurant" }));
    rerender(<MapView {...props} focusRequest={{ requestId: 2, place: places[1] }} />);
    expect(mapHarness.panTo).toHaveBeenCalledOnce();
    expect(screen.getByRole("dialog")).toHaveTextContent("Outside");
    expect(screen.queryByRole("button", { name: "Search this area" })).not.toBeInTheDocument();
  });

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
