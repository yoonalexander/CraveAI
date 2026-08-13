import { useMemo, useState } from "react";
import { GoogleMap, Marker } from "@react-google-maps/api";

import type { ChatRecommendation } from "../api/chat";
import type { Suggestion } from "../api/places";
import { useGoogleMaps } from "../context/GoogleMapsContext";
import type { SuggestionFilter } from "../utils/suggestionPool";
import {
  ClockIcon,
  DollarIcon,
  PinIcon,
  SlidersIcon,
} from "./Icons";

export type PlaceFilter = SuggestionFilter;

type MapViewProps = {
  userLocation: { lat: number; lng: number } | null;
  locationLabel: string;
  suggestions: Suggestion[];
  recommendations: ChatRecommendation[];
  activeFilters: Set<PlaceFilter>;
  hasLiveLocation: boolean;
  isLocating: boolean;
  statusMessage: string;
  radiusKm: number;
  onChangeLocation: () => void;
  onToggleFilter: (filter: PlaceFilter) => void;
  onClearFilters: () => void;
};

const mapOptions: google.maps.MapOptions = {
  clickableIcons: false,
  disableDefaultUI: true,
  fullscreenControl: false,
  gestureHandling: "cooperative",
  styles: [
    { featureType: "poi.business", stylers: [{ visibility: "off" }] },
    { featureType: "transit", stylers: [{ visibility: "off" }] },
  ],
};

export function MapView({
  userLocation,
  locationLabel,
  suggestions,
  recommendations,
  activeFilters,
  hasLiveLocation,
  isLocating,
  statusMessage,
  radiusKm,
  onChangeLocation,
  onToggleFilter,
  onClearFilters,
}: MapViewProps): JSX.Element {
  const { isLoaded, loadError, hasApiKey } = useGoogleMaps();
  const [showFilterNotice, setShowFilterNotice] = useState(false);

  const recommendationKeys = useMemo(() => {
    const keys = new Set<string>();
    recommendations.forEach((place) => {
      if (place.place_id) keys.add(`id:${place.place_id}`);
      keys.add(`name:${place.name.toLowerCase()}`);
    });
    return keys;
  }, [recommendations]);

  const recommendationNumber = (suggestion: Suggestion): number | null => {
    const index = recommendations.findIndex(
      (place) =>
        (place.place_id && place.place_id === suggestion.place_id) ||
        place.name.toLowerCase() === suggestion.name.toLowerCase(),
    );
    return index >= 0 ? index + 1 : null;
  };

  let mapContent: JSX.Element;
  if (isLocating || !userLocation) {
    mapContent = <MapLoading />;
  } else if (!hasApiKey) {
    mapContent = (
      <MapEmpty>
        Add <code>VITE_GOOGLE_MAPS_API_KEY</code> to display the live map.
      </MapEmpty>
    );
  } else if (loadError) {
    mapContent = <MapEmpty>Google Maps could not load. Your search and chat still work.</MapEmpty>;
  } else if (!isLoaded) {
    mapContent = <MapLoading />;
  } else {
    mapContent = (
      <GoogleMap
        center={userLocation}
        mapContainerStyle={{ width: "100%", height: "100%" }}
        options={mapOptions}
        zoom={hasLiveLocation ? 13 : 12}
      >
        <Marker
          label={{ text: "ME", color: "#ffffff", fontSize: "10px", fontWeight: "700" }}
          position={userLocation}
          title={hasLiveLocation ? "You are here" : locationLabel}
        />
        {suggestions.map((place) => {
          if (typeof place.lat !== "number" || typeof place.lng !== "number") return null;
          const highlighted =
            recommendationKeys.has(`id:${place.place_id}`) ||
            recommendationKeys.has(`name:${place.name.toLowerCase()}`);
          const number = recommendationNumber(place);
          return (
            <Marker
              icon={
                highlighted
                  ? undefined
                  : {
                      path: google.maps.SymbolPath.CIRCLE,
                      fillColor: "#5f8f55",
                      fillOpacity: 0.95,
                      scale: 6,
                      strokeColor: "#ffffff",
                      strokeWeight: 2,
                    }
              }
              key={place.place_id}
              label={highlighted && number ? { text: String(number), color: "#ffffff", fontWeight: "700" } : undefined}
              position={{ lat: place.lat, lng: place.lng }}
              title={place.name}
            />
          );
        })}
        {recommendations
          .filter(
            (place) =>
              typeof place.lat === "number" &&
              typeof place.lng === "number" &&
              !suggestions.some(
                (suggestion) =>
                  (place.place_id && suggestion.place_id === place.place_id) ||
                  suggestion.name.toLowerCase() === place.name.toLowerCase(),
              ),
          )
          .map((place, index) => (
            <Marker
              key={`chat-${place.place_id || place.name}-${index}`}
              label={{ text: String(index + 1), color: "#ffffff", fontWeight: "700" }}
              position={{ lat: place.lat as number, lng: place.lng as number }}
              title={place.name}
            />
          ))}
      </GoogleMap>
    );
  }

  return (
    <section className="map-card" aria-labelledby="map-title">
      <header className="map-card-header">
        <p className="eyebrow">Live map</p>
        <h2 id="map-title">Restaurants Near You</h2>
        <div className="map-location-line">
          <PinIcon />
          <div>
            <strong>{locationLabel}</strong>
            <span>{statusMessage}</span>
          </div>
        </div>
        <div className="map-filter-row" aria-label="Restaurant filters">
          <button
            aria-pressed={activeFilters.size === 0}
            className={activeFilters.size === 0 ? "is-active" : ""}
            onClick={onClearFilters}
            type="button"
          >
            <SlidersIcon /> All
          </button>
          <button
            aria-describedby="budget-filter-note"
            aria-pressed={activeFilters.has("budget")}
            className={activeFilters.has("budget") ? "is-active" : ""}
            onClick={() => onToggleFilter("budget")}
            title="Estimated from Google's lowest price levels"
            type="button"
          >
            <DollarIcon /> Under $20
          </button>
          <button
            aria-pressed={activeFilters.has("open")}
            className={activeFilters.has("open") ? "is-active" : ""}
            onClick={() => onToggleFilter("open")}
            type="button"
          >
            <ClockIcon /> Open Now
          </button>
          <div className="advanced-filter-wrap">
            <button
              aria-expanded={showFilterNotice}
              onClick={() => setShowFilterNotice((visible) => !visible)}
              type="button"
            >
              <SlidersIcon /> Filters
            </button>
            {showFilterNotice ? (
              <div className="filter-coming-soon" role="status">
                More filters are coming soon.
              </div>
            ) : null}
          </div>
        </div>
        <span className="sr-only" id="budget-filter-note">
          Under $20 is an estimate based on Google price levels zero and one.
        </span>
      </header>

      <div className="map-canvas">{mapContent}</div>

      <footer className="map-card-footer">
        <div className="map-footer-pin"><PinIcon /></div>
        <div>
          <strong>{isLocating ? "Finding nearby spots" : `You're near ${locationLabel}`}</strong>
          <span>
            {suggestions.length
              ? `${suggestions.length} spot${suggestions.length === 1 ? "" : "s"} within ${radiusKm} km`
              : "No spots match the current filters"}
          </span>
        </div>
        <button onClick={onChangeLocation} type="button">Change location</button>
      </footer>
    </section>
  );
}

function MapLoading(): JSX.Element {
  return (
    <div className="map-state">
      <div className="map-location-pulse"><span /></div>
      <strong>Finding your location</strong>
      <p>The map will appear when your location is ready.</p>
    </div>
  );
}

function MapEmpty({ children }: { children: React.ReactNode }): JSX.Element {
  return <div className="map-state"><PinIcon /><p>{children}</p></div>;
}
