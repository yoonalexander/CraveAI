import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GoogleMap, Marker, OverlayView } from "@react-google-maps/api";

import type { ChatRecommendation } from "../api/chat";
import type { Suggestion } from "../api/places";
import { useGoogleMaps } from "../context/GoogleMapsContext";
import type { Coordinates, SearchArea, ViewportBounds } from "../types/searchArea";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { PinIcon, SearchIcon } from "./Icons";

type MapViewProps = {
  originLocation: Coordinates | null;
  originIsDevice: boolean;
  locationLabel: string;
  confirmedArea: SearchArea | null;
  suggestions: Suggestion[];
  recommendations: ChatRecommendation[];
  isLocating: boolean;
  isSearching: boolean;
  recenterVersion: number;
  onSearchArea: (area: SearchArea) => void;
};

const MAX_VIEWPORT_RADIUS_METERS = 20_000;

const mapOptions: google.maps.MapOptions = {
  clickableIcons: false,
  disableDefaultUI: true,
  fullscreenControl: false,
  gestureHandling: "greedy",
  mapTypeControl: false,
  streetViewControl: false,
  zoomControl: true,
  zoomControlOptions: { position: 7 },
  styles: [
    { featureType: "poi.business", stylers: [{ visibility: "off" }] },
    { featureType: "transit", stylers: [{ visibility: "off" }] },
  ],
};

export function MapView({
  originLocation,
  originIsDevice,
  locationLabel,
  confirmedArea,
  suggestions,
  recommendations,
  isLocating,
  isSearching,
  recenterVersion,
  onSearchArea,
}: MapViewProps): JSX.Element {
  const { isLoaded, loadError, hasApiKey } = useGoogleMaps();
  const mapRef = useRef<google.maps.Map | null>(null);
  const interactionArmed = useRef(false);
  const programmaticMove = useRef(false);
  const lastRecenterVersion = useRef(-1);
  const [draftArea, setDraftArea] = useState<SearchArea | null>(null);

  const recommendationIndexes = useMemo(() => {
    const indexes = new Map<string, number>();
    recommendations.forEach((place, index) => {
      if (place.place_id) indexes.set(`id:${place.place_id}`, index + 1);
      indexes.set(`name:${place.name.toLowerCase()}`, index + 1);
    });
    return indexes;
  }, [recommendations]);

  const recenter = useCallback(() => {
    const map = mapRef.current;
    if (!map || !confirmedArea) return;
    programmaticMove.current = true;
    setDraftArea(null);
    if (confirmedArea.bounds) {
      map.fitBounds(confirmedArea.bounds, 32);
    } else {
      map.setCenter(confirmedArea.center);
      map.setZoom(13);
    }
    window.setTimeout(() => {
      programmaticMove.current = false;
      interactionArmed.current = false;
    }, 0);
  }, [confirmedArea]);

  useEffect(() => {
    if (recenterVersion === lastRecenterVersion.current) return;
    lastRecenterVersion.current = recenterVersion;
    recenter();
  }, [recenter, recenterVersion]);

  const captureViewport = () => {
    const map = mapRef.current;
    if (!map || programmaticMove.current || !interactionArmed.current) return;
    const center = map.getCenter();
    const bounds = map.getBounds();
    if (!center || !bounds) return;
    const northEast = bounds.getNorthEast();
    const southWest = bounds.getSouthWest();
    const nextBounds: ViewportBounds = {
      north: northEast.lat(),
      south: southWest.lat(),
      east: northEast.lng(),
      west: southWest.lng(),
    };
    const nextCenter = { lat: center.lat(), lng: center.lng() };
    const radius = Math.ceil(
      calculateDistanceKm(nextCenter.lat, nextCenter.lng, nextBounds.north, nextBounds.east) * 1000,
    );
    setDraftArea({ center: nextCenter, bounds: nextBounds, radius, label: "Map area" });
  };

  let content: JSX.Element;
  if (isLocating || !originLocation) {
    content = <MapState title="Finding your location">The map will appear when your location is ready.</MapState>;
  } else if (!hasApiKey) {
    content = (
      <MapState title="Map unavailable">
        Add <code>VITE_GOOGLE_MAPS_API_KEY</code> to enable viewport search. Nearby chat still works.
      </MapState>
    );
  } else if (loadError) {
    content = <MapState title="Google Maps could not load">Your current restaurant pool and chat still work.</MapState>;
  } else if (!isLoaded) {
    content = <MapState title="Loading Google Maps">This should only take a moment.</MapState>;
  } else {
    content = (
      <GoogleMap
        center={confirmedArea?.center || originLocation}
        mapContainerStyle={{ width: "100%", height: "100%" }}
        onDragStart={() => { interactionArmed.current = true; }}
        onIdle={captureViewport}
        onLoad={(map) => {
          mapRef.current = map;
          window.setTimeout(recenter, 0);
        }}
        onUnmount={() => { mapRef.current = null; }}
        onZoomChanged={captureViewport}
        options={mapOptions}
        zoom={13}
      >
        <Marker
          label={{ text: "ME", color: "#ffffff", fontSize: "10px", fontWeight: "700" }}
          position={originLocation}
          title={originIsDevice ? "You are here" : `Selected location: ${locationLabel}`}
          zIndex={1000}
        />
        {suggestions.map((place) => {
          if (!Number.isFinite(place.lat) || !Number.isFinite(place.lng)) return null;
          const recommendationNumber = recommendationIndexes.get(`id:${place.place_id}`) ||
            recommendationIndexes.get(`name:${place.name.toLowerCase()}`);
          return (
            <RestaurantMarker
              key={place.place_id}
              number={recommendationNumber}
              place={place}
            />
          );
        })}
        {recommendations
          .filter((place) =>
            typeof place.lat === "number" &&
            typeof place.lng === "number" &&
            !suggestions.some((suggestion) =>
              (place.place_id && suggestion.place_id === place.place_id) ||
              suggestion.name.toLowerCase() === place.name.toLowerCase(),
            ))
          .map((place, index) => (
            <OverlayView
              key={`chat-${place.place_id || place.name}-${index}`}
              mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
              position={{ lat: place.lat as number, lng: place.lng as number }}
            >
              <div className="restaurant-map-marker is-recommendation is-chat-only" title={place.name}>
                <span>{index + 1}</span>
              </div>
            </OverlayView>
          ))}
      </GoogleMap>
    );
  }

  const tooWide = Boolean(draftArea && draftArea.radius > MAX_VIEWPORT_RADIUS_METERS);

  return (
    <section
      aria-label="Interactive restaurant map"
      className="map-surface"
      onPointerDown={() => { interactionArmed.current = true; }}
      onWheel={() => { interactionArmed.current = true; }}
    >
      <div className="map-canvas">{content}</div>
      {draftArea ? (
        <button
          className={`search-this-area-button${tooWide ? " is-warning" : ""}`}
          disabled={isSearching || tooWide}
          onClick={() => onSearchArea(draftArea)}
          type="button"
        >
          <SearchIcon />
          {tooWide ? "Zoom in to search this area" : isSearching ? "Searching…" : "Search this area"}
        </button>
      ) : null}
      {isSearching ? <div className="map-searching-badge" role="status">Updating this map area…</div> : null}
    </section>
  );
}

function RestaurantMarker({
  place,
  number,
}: {
  place: Suggestion;
  number?: number;
}): JSX.Element {
  return (
    <OverlayView
      mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
      position={{ lat: place.lat, lng: place.lng }}
    >
      <div
        className={`restaurant-map-marker${number ? " is-recommendation" : ""}`}
        title={`${place.name}${typeof place.rating === "number" ? `, ${place.rating.toFixed(1)} stars` : ""}`}
      >
        {number ? <span>{number}</span> : null}
        <strong>{typeof place.rating === "number" ? `★ ${place.rating.toFixed(1)}` : place.name}</strong>
      </div>
    </OverlayView>
  );
}

function MapState({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="map-state">
      <PinIcon />
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
