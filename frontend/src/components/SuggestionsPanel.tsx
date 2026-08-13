import type { Suggestion } from "../api/places";
import { calculateDistanceKm } from "../utils/suggestionPool";
import { ChevronRightIcon } from "./Icons";
import { SuggestionCard } from "./SuggestionCard";

type SuggestionsPanelProps = {
  suggestions: Suggestion[];
  totalCount: number;
  isLoading: boolean;
  error: string | null;
  canRetry: boolean;
  userLocation: { lat: number; lng: number } | null;
  onRetry: () => void;
  onViewMore: () => void;
};

export function SuggestionsPanel({
  suggestions,
  totalCount,
  isLoading,
  error,
  canRetry,
  userLocation,
  onRetry,
  onViewMore,
}: SuggestionsPanelProps): JSX.Element {
  return (
    <section className="suggestions-panel" aria-labelledby="suggestions-title">
      <header className="suggestions-header">
        <div className="suggestions-title-line">
          <h2 id="suggestions-title">Today’s Suggested Spots</h2>
          <span>Powered by Google</span>
        </div>
        <p>Hand-picked picks rotating daily based on ratings, proximity, and your preferences.</p>
      </header>

      <div className="suggestions-list" aria-live="polite">
        {isLoading ? (
          <>
            <p className="suggestions-loading-copy">
              Finding nearby restaurants… The first load may take about a minute.
            </p>
            {[1, 2, 3].map((item) => <div className="suggestion-skeleton" key={item} />)}
          </>
        ) : suggestions.length ? (
          suggestions.map((suggestion) => (
            <SuggestionCard
              description={suggestion.address || suggestion.reason}
              distance={
                userLocation
                  ? `${calculateDistanceKm(
                      userLocation.lat,
                      userLocation.lng,
                      suggestion.lat,
                      suggestion.lng,
                    ).toFixed(1)} km`
                  : undefined
              }
              key={suggestion.place_id}
              placeId={suggestion.place_id}
              rating={suggestion.rating}
              tags={suggestion.tags}
              title={suggestion.name}
            />
          ))
        ) : (
          <div className="suggestions-empty">
            <strong>{error ? "Spots are unavailable right now" : "No matching spots"}</strong>
            <p>{error || "Try clearing a filter or choosing another location."}</p>
            {canRetry ? <button onClick={onRetry} type="button">Try again</button> : null}
          </div>
        )}
      </div>

      <button
        className="view-more-button"
        disabled={isLoading || totalCount <= suggestions.length}
        onClick={onViewMore}
        type="button"
      >
        <span>View more spots</span>
        <ChevronRightIcon />
      </button>
    </section>
  );
}
