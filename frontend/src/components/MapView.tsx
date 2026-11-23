import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GoogleMap, InfoWindow, Marker, OVERLAY_MOUSE_TARGET, OverlayViewF } from "@react-google-maps/api";
import { FilterEvidence } from "./FilterEvidence";

import type { ChatRecommendation } from "../api/chat";
import { catalogSourceForId, type Suggestion } from "../api/places";
import { CatalogListingDetails } from "./CatalogListingDetails";
import { useGoogleMaps } from "../context/GoogleMapsContext";
import type { Coordinates, SearchArea, ViewportBounds } from "../types/searchArea";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { recordStartupTiming } from "../utils/startupTelemetry";
import { PinIcon, SearchIcon } from "./Icons";
import { LocationLoader } from "./LoadingIndicators";
import { RestaurantPhotos } from "./RestaurantPhotos";
import { MapRestaurantList } from "./MapRestaurantList";
import { getMapRestaurants, hasMapCoordinates as hasCoordinates, sameMapRestaurant, type MapRestaurant } from "../utils/mapRestaurants";

type MapViewProps = {
  originLocation: Coordinates | null;
  originIsDevice: boolean;
  locationLabel: string;
  confirmedArea: SearchArea | null;
  suggestions: Suggestion[];
  recommendations: ChatRecommendation[];
  focusRequest?: { requestId: number; place: ChatRecommendation } | null;
  isLocating: boolean;
  isSearching: boolean;
  recenterVersion: number;
  onSearchArea: (area: SearchArea) => void;
  listOpen?: boolean;
  resultsAreaLabel?: string;
  onListOpenChange?: (open: boolean) => void;
  error?: string | null;
  coverageNotice?: string | null;
  canRetry?: boolean;
  onRetry?: () => void;
};

const MAX_VIEWPORT_RADIUS_METERS = 20_000;
const MAP_STYLE_STORAGE_KEY = "craveai:map-style:v1";
const MAP_STYLE_LABELS = { standard: "Standard", minimal: "Minimal", dark: "Dark", satellite: "Satellite" };
type MapStyle = keyof typeof MAP_STYLE_LABELS;

const mapOptions: google.maps.MapOptions = {
  clickableIcons: false,
  disableDefaultUI: true,
  fullscreenControl: false,
  gestureHandling: "greedy",
  mapTypeControl: false,
  streetViewControl: false,
  zoomControl: true,
  zoomControlOptions: { position: 7 },
};

const standardStyles: google.maps.MapTypeStyle[] = [
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];

const mapOptionsByStyle: Record<MapStyle, google.maps.MapOptions> = {
  standard: { ...mapOptions, mapTypeId: "roadmap", styles: standardStyles },
  minimal: { ...mapOptions, mapTypeId: "roadmap", styles: [
    { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
    { featureType: "road.local", elementType: "labels", stylers: [{ visibility: "off" }] },
    { featureType: "transit", stylers: [{ visibility: "off" }] },
  ] },
  dark: { ...mapOptions, mapTypeId: "roadmap", styles: [
    ...standardStyles,
    { elementType: "geometry", stylers: [{ color: "#252d33" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#c5d0d6" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#252d33" }] },
    { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#52616b" }] },
    { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#2d4238" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#43515b" }] },
    { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#303b43" }] },
    { featureType: "road.highway", elementType: "geometry.fill", stylers: [{ color: "#6a6856" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#172b3a" }] },
  ] },
  satellite: { ...mapOptions, mapTypeId: "hybrid", styles: null },
};

function isMapStyle(value: string | null): value is MapStyle {
  return value !== null && Object.prototype.hasOwnProperty.call(MAP_STYLE_LABELS, value);
}

function readMapStyle(): MapStyle {
  try {
    const saved = window.localStorage.getItem(MAP_STYLE_STORAGE_KEY);
    return isMapStyle(saved) ? saved : "standard";
  } catch {
    return "standard";
  }
}

export function MapView({
  originLocation,
  originIsDevice,
  locationLabel,
  confirmedArea,
  suggestions,
  recommendations,
  focusRequest,
  isLocating,
  isSearching,
  recenterVersion,
  onSearchArea,
  listOpen,
  resultsAreaLabel,
  onListOpenChange,
  error = null,
  coverageNotice = null,
  canRetry = false,
  onRetry,
}: MapViewProps): JSX.Element {
  const { isLoaded, loadError, hasApiKey } = useGoogleMaps();
  const mapRef = useRef<google.maps.Map | null>(null);
  const interactionArmed = useRef(false);
  const programmaticMove = useRef(false);
  const lastRecenterVersion = useRef(-1);
  const [draftArea, setDraftArea] = useState<SearchArea | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<Suggestion | ChatRecommendation | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [localListOpen, setLocalListOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState(readMapStyle);
  const mapButton = useRef<HTMLButtonElement>(null);
  const showList = listOpen ?? localListOpen;
  const entries = useMemo(() => getMapRestaurants(suggestions, recommendations), [suggestions, recommendations]);
  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const changeListOpen = (open: boolean) => { setLocalListOpen(open); onListOpenChange?.(open); };

  useEffect(() => {
    if (selectedKey) {
      const entry = entries.find((entry) => entry.key === selectedKey);
      if (entry) setSelectedPlace(entry.place);
      else { setSelectedKey(null); setSelectedPlace(null); }
    }
  }, [entries, selectedKey]);

  const selectPlace = useCallback((place: Suggestion | ChatRecommendation, key?: string) => {
    const map = mapRef.current;
    if (!map || !hasCoordinates(place)) return;
    programmaticMove.current = true;
    interactionArmed.current = false;
    setDraftArea(null);
    setSelectedPlace(place);
    setSelectedKey(key || null);
    map.panTo({ lat: place.lat, lng: place.lng });
  }, []);

  const recenter = useCallback(() => {
    const map = mapRef.current;
    if (!map || !confirmedArea) return;
    programmaticMove.current = true;
    interactionArmed.current = false;
    setDraftArea(null);
    setSelectedPlace(null);
    setSelectedKey(null);
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
    if (!mapReady) return;
    if (recenterVersion === lastRecenterVersion.current) return;
    lastRecenterVersion.current = recenterVersion;
    recenter();
  }, [mapReady, recenter, recenterVersion]);

  useEffect(() => {
    if (!mapReady || !focusRequest || !hasCoordinates(focusRequest.place)) return;
    const focusedPlace = focusRequest.place;
    const entry = entriesRef.current.find((entry) => sameMapRestaurant(entry.place, focusedPlace));
    selectPlace(entry?.place || focusedPlace, entry?.key);
    const map = mapRef.current;
    if (map && (map.getZoom() ?? 13) < 16) map.setZoom(16);
  }, [focusRequest, mapReady, selectPlace]);

  const captureViewport = () => {
    const map = mapRef.current;
    if (!map) return;
    if (programmaticMove.current) {
      programmaticMove.current = false;
      return;
    }
    if (!interactionArmed.current) return;
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
    content = <MapState loading title="Finding your location">The map will appear when your location is ready.</MapState>;
  } else if (!hasApiKey) {
    content = (
      <MapState title="Map unavailable">
        Add <code>VITE_GOOGLE_MAPS_API_KEY</code> to enable viewport search. Nearby chat still works.
      </MapState>
    );
  } else if (loadError) {
    content = <MapState title="Google Maps could not load">Your current restaurant pool and chat still work.</MapState>;
  } else if (!isLoaded) {
    content = <MapState loading title="Loading Google Maps">This should only take a moment.</MapState>;
  } else {
    content = (
      <GoogleMap
        center={confirmedArea?.center || originLocation}
        mapContainerStyle={{ width: "100%", height: "100%" }}
        onDragStart={() => { programmaticMove.current = false; interactionArmed.current = true; }}
        onIdle={captureViewport}
        onLoad={(map) => {
          mapRef.current = map;
          recordStartupTiming("first_map_render", "success");
          setMapReady(true);
        }}
        onUnmount={() => { mapRef.current = null; setMapReady(false); }}
        onZoomChanged={captureViewport}
        options={mapOptionsByStyle[mapStyle]}
        zoom={13}
      >
        <Marker
          label={{ text: "ME", color: "#ffffff", fontFamily: "var(--font-family-sans)", fontSize: "10px", fontWeight: "700" }}
          position={originLocation}
          title={originIsDevice ? "You are here" : `Selected location: ${locationLabel}`}
          zIndex={1000}
        />
        {entries.map((entry) => entry.recommendationNumber === undefined ? null : (
          <RestaurantMarker
            key={entry.key}
            entry={entry}
            number={entry.recommendationNumber}
            onSelect={selectPlace}
          />
        ))}
        {selectedPlace && hasCoordinates(selectedPlace) ? (
          <InfoWindow
            onCloseClick={() => { setSelectedPlace(null); setSelectedKey(null); }}
            position={{ lat: selectedPlace.lat, lng: selectedPlace.lng }}
          >
            <div className="restaurant-map-popup">
              <RestaurantPhotos placeId={selectedPlace.place_id} title={selectedPlace.name} />
              <strong>{selectedPlace.name}</strong>
              {typeof selectedPlace.rating === "number" ? <span>★ {selectedPlace.rating.toFixed(1)}</span> : null}
              {selectedPlace.address ? <p>{selectedPlace.address}</p> : null}
              {"checked_on" in selectedPlace ? <CatalogListingDetails place={selectedPlace} /> : null}
              {"cuisine_labels" in selectedPlace ? <FilterEvidence labels={[...(selectedPlace.cuisine_labels || []), ...(selectedPlace.dietary_labels || [])]} /> : null}
              {selectedPlace.place_id ? (
                <a href={catalogSourceForId(selectedPlace.place_id)
                  ? `https://www.google.com/maps/search/?api=1&query=${selectedPlace.lat},${selectedPlace.lng}`
                  : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(selectedPlace.name)}&query_place_id=${encodeURIComponent(selectedPlace.place_id)}`} rel="noreferrer" target="_blank">
                  Open in Google Maps
                </a>
              ) : null}
            </div>
          </InfoWindow>
        ) : null}
      </GoogleMap>
    );
  }

  const tooWide = Boolean(draftArea && draftArea.radius > MAX_VIEWPORT_RADIUS_METERS);

  return (
    <section
      aria-label="Interactive restaurant map"
      className={`map-surface${showList ? " is-list-open" : ""}`}
      onKeyDown={(event) => {
        if (showList && event.key === "Escape" && !(event.target as HTMLElement).closest("[role='dialog']")) {
          changeListOpen(false); mapButton.current?.focus();
        }
      }}
      onPointerDown={(event) => { if (!showList && (event.target as HTMLElement).closest(".map-canvas")) interactionArmed.current = true; }}
      onWheel={(event) => { if (!showList && (event.target as HTMLElement).closest(".map-canvas")) interactionArmed.current = true; }}
    >
      <div className="map-view-control" role="group" aria-label="Restaurant view">
        <button ref={mapButton} type="button" aria-pressed={!showList} aria-controls="restaurant-map-canvas" onClick={() => changeListOpen(false)}><PinIcon />Map</button>
        <button type="button" aria-pressed={showList} aria-controls="map-restaurant-results" onClick={() => changeListOpen(true)}>List <span>{entries.length}</span></button>
        {!showList && mapReady ? (
          <select aria-label="Map style" className="map-style-picker" value={mapStyle} onChange={(event) => {
            const style = event.currentTarget.value;
            if (!isMapStyle(style)) return;
            setMapStyle(style);
            try {
              window.localStorage.setItem(MAP_STYLE_STORAGE_KEY, style);
            } catch {
              // The selected style still works when browser storage is unavailable.
            }
          }}>
            {Object.entries(MAP_STYLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        ) : null}
      </div>
      <div className="map-canvas" id="restaurant-map-canvas" aria-hidden={showList}>{content}</div>
      {showList ? <div id="map-restaurant-results" className="map-list-surface"><MapRestaurantList
        entries={entries} selectedKey={selectedKey} origin={originLocation} areaLabel={resultsAreaLabel || confirmedArea?.label || locationLabel}
        isLoading={isSearching || isLocating} error={error} coverageNotice={coverageNotice} canRetry={canRetry} onRetry={onRetry}
        mapAvailable={mapReady && isLoaded && !loadError && hasApiKey}
        onSelect={(entry) => {
          selectPlace(entry.place, entry.key);
          if (mapRef.current && (mapRef.current.getZoom() ?? 13) < 16) mapRef.current.setZoom(16);
          changeListOpen(false); mapButton.current?.focus();
        }} />
      </div> : null}
      {!showList && draftArea ? (
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
      {!showList && isSearching ? <div className="map-searching-badge" role="status">Updating this map area…</div> : null}
    </section>
  );
}

const RestaurantMarker = memo(function RestaurantMarker({
  entry,
  number,
  onSelect,
}: {
  entry: MapRestaurant;
  number: number;
  onSelect: (place: MapRestaurant["place"], key: string) => void;
}): JSX.Element {
  const { place } = entry;
  const { lat, lng } = place;
  // OverlayViewF reattaches its Maps overlay if the position object changes.
  const position = useMemo(() => ({ lat, lng }), [lat, lng]);
  return (
    <OverlayViewF
      mapPaneName={OVERLAY_MOUSE_TARGET}
      position={position}
    >
      <button
        aria-label={`Show ${place.name} on map`}
        onClick={() => onSelect(place, entry.key)}
        type="button"
        className="restaurant-map-marker"
        title={place.name}
      >
        <span>{number}</span>
      </button>
    </OverlayViewF>
  );
});

function MapState({ title, children, loading = false }: { title: string; children: React.ReactNode; loading?: boolean }): JSX.Element {
  return (
    <div className="map-state" role="status">
      {loading ? <LocationLoader large /> : <PinIcon />}
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
