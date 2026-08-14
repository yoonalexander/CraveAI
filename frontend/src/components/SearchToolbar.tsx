import { useEffect, useRef, useState } from "react";

import type { SearchArea } from "../types/searchArea";
import type { AdvancedFilters, SuggestionFilter } from "../utils/suggestionPool";
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
  advancedFilters: AdvancedFilters;
  onAdvancedFiltersChange: (filters: AdvancedFilters) => void;
  dietaryVerification?: { loading: boolean; error: string | null };
  onRetryDietaryVerification?: () => void;
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
  advancedFilters,
  onAdvancedFiltersChange,
  dietaryVerification = { loading: false, error: null },
  onRetryDietaryVerification = () => undefined,
}: SearchToolbarProps): JSX.Element {
  const [showMore, setShowMore] = useState(false);
  const [draftFilters, setDraftFilters] = useState(advancedFilters);
  const moreRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!showMore) return;
    const close = (event: MouseEvent) => {
      if ((event.target as Element).closest?.(".advanced-filter-dialog")) return;
      if (!moreRef.current?.contains(event.target as Node)) setShowMore(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [showMore]);

  useEffect(() => {
    if (!showMore) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>("button, input, select, [href], [tabindex]:not([tabindex='-1'])") || []).filter((item) => !item.hasAttribute("disabled"));
    focusable()[0]?.focus();
    const handleKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { setShowMore(false); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); previous?.focus(); };
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
            onClick={() => { setDraftFilters(advancedFilters); setShowMore((open) => !open); }}
            type="button"
          >
            <SlidersIcon /> Filters
          </button>
        </div>
      </div>
      <span className="sr-only" id="budget-filter-explanation">
        Under $20 is estimated from Google price levels zero and one.
      </span>
      {advancedFilters.dietary.length ? <div className={`dietary-verification-status${dietaryVerification.error ? " is-error" : ""}`} aria-live="polite">{dietaryVerification.loading ? "Checking official menus without hiding current results…" : dietaryVerification.error ? <>{dietaryVerification.error} <button onClick={onRetryDietaryVerification}>Retry</button></> : "Only restaurants with attributable official-menu matches are shown. Coverage may be limited."}</div> : null}
      {showMore ? (
        <div className="advanced-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowMore(false); }}>
          <section aria-labelledby="advanced-filter-title" aria-modal="true" className="advanced-filter-dialog" ref={dialogRef} role="dialog">
            <header><div><p>Filters</p><h2 id="advanced-filter-title">Find the right restaurant</h2></div><button aria-label="Close filters" onClick={() => setShowMore(false)}>×</button></header>
            <div className="advanced-filter-fields">
              <label>Cuisine<input onChange={(event) => setDraftFilters({ ...draftFilters, cuisine: event.target.value })} placeholder="e.g. Japanese" value={draftFilters.cuisine} /></label>
              <label>Minimum rating<select onChange={(event) => setDraftFilters({ ...draftFilters, minimumRating: Number(event.target.value) })} value={draftFilters.minimumRating}><option value="0">Any rating</option><option value="4">4.0+</option><option value="4.5">4.5+</option></select></label>
              <label>Maximum distance<select onChange={(event) => setDraftFilters({ ...draftFilters, maximumDistanceKm: Number(event.target.value) })} value={draftFilters.maximumDistanceKm}><option value="2">2 km</option><option value="5">5 km</option><option value="10">10 km</option><option value="20">Any in map area</option></select></label>
              <label>Sort by<select onChange={(event) => setDraftFilters({ ...draftFilters, sort: event.target.value as AdvancedFilters["sort"] })} value={draftFilters.sort}><option value="relevance">Relevance</option><option value="rating">Rating</option><option value="distance">Distance</option><option value="price">Price</option></select></label>
            </div>
            <fieldset><legend>Price level</legend><div className="filter-checkbox-grid">{[0, 1, 2, 3, 4].map((level) => <label key={level}><input checked={draftFilters.priceLevels.includes(level)} onChange={(event) => setDraftFilters({ ...draftFilters, priceLevels: event.target.checked ? [...draftFilters.priceLevels, level] : draftFilters.priceLevels.filter((item) => item !== level) })} type="checkbox" />{level === 0 ? "Free / no cost data" : "$".repeat(level)}</label>)}</div></fieldset>
            <fieldset><legend>Verified provider attributes</legend><div className="filter-checkbox-grid">{[["takeout", "Takeout"], ["delivery", "Delivery"], ["reservations", "Reservations"], ["accessibility", "Accessible entrance"]].map(([key, label]) => <label key={key}><input checked={draftFilters[key as keyof AdvancedFilters] === true} onChange={(event) => setDraftFilters({ ...draftFilters, [key]: event.target.checked })} type="checkbox" />{label}</label>)}</div><small>When selected, places with unknown provider data are excluded.</small></fieldset>
            <fieldset><legend>Dietary menu evidence</legend><div className="filter-checkbox-grid">{["vegetarian", "vegan", "gluten-free", "halal"].map((item) => <label key={item}><input checked={draftFilters.dietary.includes(item)} onChange={(event) => setDraftFilters({ ...draftFilters, dietary: event.target.checked ? [...draftFilters.dietary, item] : draftFilters.dietary.filter((entry) => entry !== item) })} type="checkbox" />{item}</label>)}</div><small>Only attributable official-menu matches qualify. Coverage may be limited and never guarantees allergen safety.</small></fieldset>
            <footer><button onClick={() => setDraftFilters({ ...advancedFilters, cuisine: "", minimumRating: 0, maximumDistanceKm: 20, priceLevels: [], takeout: false, delivery: false, reservations: false, accessibility: false, dietary: [], sort: "relevance" })}>Clear</button><button className="primary-action" onClick={() => { onAdvancedFiltersChange(draftFilters); setShowMore(false); }}>Show results</button></footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
