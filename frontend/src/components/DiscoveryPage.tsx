import { useMemo, useState } from "react";

import type { Suggestion } from "../api/places";
import type { Coordinates } from "../types/searchArea";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { SuggestionCard } from "./SuggestionCard";

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
  const [collection, setCollection] = useState("all");
  const cuisineGroups = useMemo(
    () => Array.from(new Set(suggestions.flatMap((item) => item.tags || []))).sort().slice(0, 8),
    [suggestions],
  );
  const visible = useMemo(() => suggestions.filter((item) => {
    const haystack = `${item.name} ${item.address} ${(item.tags || []).join(" ")}`.toLowerCase();
    if (query && !haystack.includes(query.toLowerCase())) return false;
    if (collection === "top" && item.rating < 4.5) return false;
    if (collection === "budget" && (typeof item.price_level !== "number" || item.price_level > 1)) return false;
    if (collection === "open" && item.open_now !== true) return false;
    if (collection.startsWith("cuisine:")) return (item.tags || []).includes(collection.slice(8));
    return true;
  }), [collection, query, suggestions]);
  return (
    <section className="discovery-page" aria-labelledby="discovery-title">
      <header className="discovery-heading">
        <div>
          <p>Discovery</p>
          <h1 id="discovery-title">Today’s Suggested Spots</h1>
        </div>
        <span>Powered by Google</span>
      </header>
      <p className="discovery-intro">
        Explore every restaurant in your confirmed map area. Move the map on Home and choose Search this area to refresh this collection.
      </p>

      <div className="discovery-controls">
        <label><span>Search restaurants</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Name, cuisine, or address" value={query} /></label>
        <div className="discovery-collections" aria-label="Data-driven collections">
          {[["all", "All"], ["top", "Top Rated"], ["budget", "Budget-Friendly"], ["open", "Open Now"], ...cuisineGroups.map((item) => [`cuisine:${item}`, item])].map(([value, label]) => <button aria-pressed={collection === value} className={collection === value ? "is-active" : ""} key={value} onClick={() => setCollection(value)}>{label}</button>)}
        </div>
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
              title={suggestion.name}
            />
          ))}
        </div>
      ) : (
        <div className="discovery-empty" aria-live="polite">
          <img alt="" src="/craveai-pin.svg" />
          <h2>{isLoading ? "Finding restaurants…" : "No spots to show yet"}</h2>
          <p>{error || "Try clearing a filter or confirm another map area from Home."}</p>
          {!isLoading && canRetry ? <button onClick={onRetry} type="button">Try again</button> : null}
        </div>
      )}
    </section>
  );
}
