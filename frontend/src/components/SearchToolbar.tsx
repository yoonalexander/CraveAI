import { useEffect, useRef, useState } from "react";

import type { SearchArea } from "../types/searchArea";
import type { SuggestionFilter } from "../utils/suggestionPool";
import { ClockIcon, DollarIcon, PinIcon, SlidersIcon } from "./Icons";

type SearchToolbarProps = {
  area: SearchArea | null;
  activeFilters: Set<SuggestionFilter>;
  count: number;
  error: string | null;
  isLoading: boolean;
  canRetry: boolean;
  onChangeLocation: () => void;
  onClearFilters: () => void;
  onRetry: () => void;
  onToggleFilter: (filter: SuggestionFilter) => void;
};

export function SearchToolbar({
  area,
  activeFilters,
  count,
  error,
  isLoading,
  canRetry,
  onChangeLocation,
  onClearFilters,
  onRetry,
  onToggleFilter,
}: SearchToolbarProps): JSX.Element {
  const [showMore, setShowMore] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showMore) return;
    const close = (event: MouseEvent) => {
      if (!moreRef.current?.contains(event.target as Node)) setShowMore(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [showMore]);

  const status = isLoading
    ? count
      ? `Updating ${count} restaurant${count === 1 ? "" : "s"}…`
      : "Finding restaurants…"
    : error
      ? error
      : `${count} restaurant${count === 1 ? "" : "s"} in this area`;

  return (
    <section
      className={`search-toolbar${error ? " has-error" : ""}${isLoading ? " is-loading" : ""}`}
      aria-label="Restaurant search controls"
    >
      <div className="search-toolbar-location">
        <span className="search-toolbar-pin"><PinIcon /></span>
        <div>
          <span>Search area</span>
          <strong>{area?.label || "Finding your location…"}</strong>
        </div>
        <button onClick={onChangeLocation} type="button">Change location</button>
      </div>

      <div className="search-toolbar-status" aria-live="polite">
        <span className={error ? "is-error" : ""}>{status}</span>
        {error && canRetry ? <button onClick={onRetry} type="button">Try again</button> : null}
      </div>

      <div className="search-filter-scroll" aria-label="Restaurant filters">
        <button
          aria-pressed={activeFilters.size === 0}
          className={activeFilters.size === 0 ? "is-active" : ""}
          onClick={onClearFilters}
          type="button"
        >
          <SlidersIcon /> All
        </button>
        <button
          aria-describedby="budget-filter-explanation"
          aria-pressed={activeFilters.has("budget")}
          className={activeFilters.has("budget") ? "is-active" : ""}
          onClick={() => onToggleFilter("budget")}
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
        <div className="toolbar-more-filter" ref={moreRef}>
          <button
            aria-expanded={showMore}
            onClick={() => setShowMore((open) => !open)}
            type="button"
          >
            <SlidersIcon /> Filters
          </button>
          {showMore ? <div className="toolbar-filter-popover" role="status">More filters are coming soon.</div> : null}
        </div>
      </div>
      <span className="sr-only" id="budget-filter-explanation">
        Under $20 is estimated from Google price levels zero and one.
      </span>
    </section>
  );
}
