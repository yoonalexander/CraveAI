import { useMemo, useState } from "react";

import type { Suggestion } from "../api/places";
import type { Coordinates } from "../types/searchArea";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { SuggestionCard } from "./SuggestionCard";
import { CuisineIcon } from "./CuisineIcon";

type DiscoveryPageProps = {
  suggestions: Suggestion[];
  origin: Coordinates | null;
  isLoading: boolean;
  error: string | null;
  canRetry: boolean;
  onRetry: () => void;
};

export function DiscoveryPage({
  suggestions,
  origin,
  isLoading,
  error,
  canRetry,
  onRetry,
}: DiscoveryPageProps): JSX.Element {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => suggestions.filter((item) => {
    const haystack = `${item.name} ${item.address} ${(item.tags || []).join(" ")} ${(item.cuisine_labels || []).map((label) => label.value).join(" ")}`.toLowerCase();
    return !query.trim() || haystack.includes(query.trim().toLowerCase());
  }), [query, suggestions]);
  return (
    <section className="discovery-page" aria-labelledby="discovery-title">
      <header className="discovery-heading">
        <div>
          <p>Discovery</p>
          <h1 id="discovery-title">Today’s Suggested Spots</h1>
        </div>
        <a href="https://maps.google.com/" rel="noreferrer" target="_blank">Restaurant data by Google Maps</a>
      </header>
      <p className="discovery-intro">
        Explore restaurants in your confirmed map area. Filters and sorting above also apply on Home. Move the map on Home and choose Search this area to refresh this collection.
      </p>

      <div className="discovery-controls">
        <label><span>Search this collection</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Name, cuisine, or address" value={query} /></label>
        {query ? <button onClick={() => setQuery("")} type="button">Clear search</button> : null}
        <p role="status">{visible.length} of {suggestions.length} filtered restaurants in this collection</p>
      </div>

      {visible.length ? (
        <div className="discovery-grid" aria-live="polite">
          {visible.map((suggestion) => (
            <SuggestionCard
              description={suggestion.address || suggestion.reason}
              distance={origin
                ? `${calculateDistanceKm(origin.lat, origin.lng, suggestion.lat, suggestion.lng).toFixed(1)} km`
                : undefined}
              key={suggestion.place_id}
              placeId={suggestion.place_id}
              rating={suggestion.rating}
              tags={suggestion.tags}
              cuisineLabels={suggestion.cuisine_labels}
              filterLabels={[...(suggestion.cuisine_labels || []), ...(suggestion.dietary_labels || [])]}
              title={suggestion.name}
            />
          ))}
        </div>
      ) : (
        <div className="discovery-empty" aria-live="polite">
          <CuisineIcon />
          <h2>{isLoading ? "Finding restaurants…" : "No spots to show yet"}</h2>
          <p>{error || "Try clearing a filter or confirm another map area from Home."}</p>
          {!isLoading && canRetry ? <button onClick={onRetry} type="button">Try again</button> : null}
        </div>
      )}
    </section>
  );
}
