import type { Coordinates } from "../types/searchArea";
import type { MapRestaurant } from "../utils/mapRestaurants";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { FilterEvidence } from "./FilterEvidence";
import { PinIcon } from "./Icons";
import { RestaurantPhotos } from "./RestaurantPhotos";

export function MapRestaurantList({ entries, selectedKey, origin, areaLabel, isLoading, error, coverageNotice, canRetry, onRetry, onSelect, mapAvailable }: {
  entries: MapRestaurant[];
  selectedKey: string | null;
  origin: Coordinates | null;
  areaLabel: string;
  isLoading: boolean;
  error: string | null;
  coverageNotice: string | null;
  canRetry: boolean;
  onRetry?: () => void;
  onSelect: (entry: MapRestaurant) => void;
  mapAvailable: boolean;
}): JSX.Element {
  const chatCount = entries.filter((entry) => entry.source === "chat").length;
  return <section className="map-restaurant-list" aria-labelledby="map-list-title">
    <header><p>{areaLabel}</p><h2 id="map-list-title">Restaurants on this map</h2>
      <p role="status">{entries.length} restaurant{entries.length === 1 ? "" : "s"}{chatCount ? ` · ${chatCount} added from chat` : ""}</p>
      <p>All loaded pins, not just the visible map. Nearby pins follow filters; chat picks stay included.</p>
      {!mapAvailable ? <p>In-app map is not ready. Google Maps links are available.</p> : null}
      {isLoading ? <p role="status">Updating restaurants… {entries.length ? "Current pins remain available until the search finishes." : "The first load may take about a minute."}</p> : null}
      {error ? <div className="map-list-notice" role="alert"><p>{error}</p>{canRetry && onRetry ? <button type="button" onClick={onRetry} disabled={isLoading}>Try again</button> : null}</div> : null}
      {coverageNotice ? <p className="map-list-notice">{coverageNotice}</p> : null}
    </header>
    {entries.length ? <ul aria-label="Pinned restaurants">{entries.map((entry) => {
      const place = entry.place;
      const query = new URLSearchParams({ api: "1", query: `${place.lat},${place.lng}` });
      if (place.place_id) { query.set("query", place.name); query.set("query_place_id", place.place_id); }
      const rating = typeof place.rating === "number" && Number.isFinite(place.rating) ? place.rating.toFixed(1) : null;
      return <li key={entry.key}><article className={`map-list-card${selectedKey === entry.key ? " is-selected" : ""}`}>
        <RestaurantPhotos placeId={place.place_id} title={place.name} compact />
        <div className="map-list-card-body">
          {entry.recommendationNumber ? <p className="map-list-chat-label">Chat pick {entry.recommendationNumber}</p> : null}
          <h3>{place.name}</h3>
          <p>{rating ? `★ ${rating}` : "Rating unavailable"}{origin ? ` · ${calculateDistanceKm(origin.lat, origin.lng, place.lat, place.lng).toFixed(1)} km away` : ""}</p>
          <p>{place.address || "Address unavailable"}</p>
          {"cuisine_labels" in place ? <FilterEvidence labels={[...(place.cuisine_labels || []), ...(place.dietary_labels || [])]} /> : null}
          <div className="map-list-actions"><button type="button" disabled={!mapAvailable} aria-label={`Show ${place.name} on map`} aria-pressed={selectedKey === entry.key} onClick={() => onSelect(entry)}><PinIcon />Show on map</button>
            <a href={`https://www.google.com/maps/search/?${query}`} target="_blank" rel="noreferrer">Open in Google Maps</a></div>
        </div>
      </article></li>;
    })}</ul> : !isLoading ? <div className="map-list-empty"><PinIcon /><h3>{error ? "Restaurants are unavailable" : "No restaurant pins to show"}</h3><p>{error ? "Try the search again or choose another area." : "Clear a filter or choose another search area. You can browse without starting a chat."}</p></div> : null}
    <a className="map-list-attribution" href="https://maps.google.com/" target="_blank" rel="noreferrer">Restaurant data by Google Maps</a>
  </section>;
}
