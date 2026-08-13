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

      {suggestions.length ? (
        <div className="discovery-grid" aria-live="polite">
          {suggestions.map((suggestion) => (
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
