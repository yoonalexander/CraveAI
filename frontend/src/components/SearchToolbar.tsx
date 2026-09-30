import { useEffect, useRef, useState } from "react";

import type { SearchArea } from "../types/searchArea";
import type { Suggestion } from "../api/places";
import type { AdvancedFilters, SuggestionFilter } from "../utils/suggestionPool";
import { advancedFilterSummary, CUISINE_OPTIONS, DEFAULT_ADVANCED_FILTERS } from "../utils/suggestionPool";
import { ClockIcon, DollarIcon, PinIcon, SlidersIcon } from "./Icons";
import { LocationLoader } from "./LoadingIndicators";

type SearchToolbarProps = {
  area: SearchArea | null;
  activeFilters: Set<SuggestionFilter>;
  count: number;
  totalCount?: number;
  coverageNotice?: string | null;
  error: string | null;
  isLoading: boolean;
  canRetry: boolean;
  onChangeLocation: () => void;
  onClearFilters: () => void;
  onRetry: () => void;
  onToggleFilter: (filter: SuggestionFilter) => void;
  advancedFilters: AdvancedFilters;
  onAdvancedFiltersChange: (filters: AdvancedFilters) => void;
  filterDataStatus?: { loading: boolean; error: string | null; checked: number; menus: number; remaining: number; unavailable: number };
  filterDataPlaces?: Suggestion[];
  onCheckFilterData?: () => void;
};

export function SearchToolbar({
  area,
  activeFilters,
  count,
  totalCount = count,
  coverageNotice,
  error,
  isLoading,
  canRetry,
  onChangeLocation,
  onClearFilters,
  onRetry,
  onToggleFilter,
  advancedFilters,
  onAdvancedFiltersChange,
  filterDataStatus = { loading: false, error: null, checked: 0, menus: 0, remaining: 0, unavailable: 0 },
  filterDataPlaces = [],
  onCheckFilterData = () => undefined,
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

  const summary = advancedFilterSummary(advancedFilters);
  const hasFilters = activeFilters.size > 0 || summary.length > 0;
  const needsData = Boolean(advancedFilters.cuisine || advancedFilters.dietary.length || advancedFilters.takeout || advancedFilters.delivery || advancedFilters.reservations || advancedFilters.accessibility);
  const status = isLoading
    ? count
      ? `Updating ${count} restaurant${count === 1 ? "" : "s"}…`
      : "Finding restaurants…"
    : error
      ? error
      : hasFilters || count !== totalCount
        ? `${count} of ${totalCount} loaded restaurants shown`
        : `${count} restaurant${count === 1 ? "" : "s"} in this area`;

  return (
    <section
      className={`search-toolbar${error ? " has-error" : ""}${isLoading ? " is-loading" : ""}${hasFilters || count !== totalCount ? " has-filtered-results" : ""}`}
      aria-label="Restaurant search controls"
    >
      <div className="search-toolbar-location">
        <span className="search-toolbar-pin">{area ? <PinIcon /> : <LocationLoader />}</span>
        <div role="status">
          <span>Search area</span>
          <strong>{area?.label || "Finding your location…"}</strong>
        </div>
        <button onClick={onChangeLocation} type="button">Change location</button>
      </div>

      <div className="search-toolbar-status" aria-live="polite">
        <span className={error ? "is-error" : ""}>{status}</span>
        {error && canRetry ? <button onClick={onRetry} type="button">Try again</button> : null}
        {!isLoading && hasFilters ? <button onClick={onClearFilters} type="button">Clear filters</button> : null}
      </div>

      <div className="search-filter-scroll" aria-label="Restaurant filters">
        <button
          aria-pressed={!hasFilters}
          className={!hasFilters ? "is-active" : ""}
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
          <DollarIcon /> Budget-friendly
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
            <SlidersIcon /> Filters{summary.length ? ` (${summary.length})` : ""}
          </button>
        </div>
      </div>
      {!isLoading && coverageNotice ? <p className="discovery-coverage-notice" role="status">{coverageNotice}</p> : null}
      <span className="sr-only" id="budget-filter-explanation">
        Budget-friendly includes Google price levels free and inexpensive. It does not guarantee a meal under a dollar amount.
      </span>
      {summary.length ? <div className="active-filter-summary" aria-label="Selected advanced filters">{summary.map(({ key, label }) => <button key={key} aria-label={`Remove ${label} filter`} onClick={() => onAdvancedFiltersChange({ ...advancedFilters, [key]: DEFAULT_ADVANCED_FILTERS[key] })}>{label} ×</button>)}</div> : null}
      <details className="filter-data-coverage" open={needsData || undefined}>
        <summary>Restaurant data: {filterDataStatus.checked} of {totalCount} details checked</summary>
        <p>Unknown attributes are excluded by selected filters. Cuisine labels come from Google types or menu inference; restaurant-name guesses do not qualify. {filterDataStatus.menus} official menus assessed.</p>
        <p>{filterDataPlaces.filter((place) => place.cuisine_labels?.length).length} with cuisine labels. Menu labels use GPT to interpret official sources and can be excluded in Filters.</p>
        {filterDataStatus.unavailable ? <p>{filterDataStatus.unavailable} restaurant checks have unavailable details or menu labeling. Missing evidence does not mean the restaurant lacks an option.</p> : null}
        {filterDataStatus.error ? <p role="alert">{filterDataStatus.error}</p> : null}
        <div aria-live="polite">{filterDataStatus.loading ? "Checking Google details and official menus…" : null}</div>
        {filterDataStatus.remaining || filterDataStatus.unavailable ? <button disabled={filterDataStatus.loading || isLoading} onClick={onCheckFilterData} type="button">{filterDataStatus.remaining ? `Check next ${Math.min(10, filterDataStatus.remaining)} restaurants` : "Retry unavailable details"}</button> : null}
      </details>
      {showMore ? (
        <div className="advanced-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowMore(false); }}>
          <section aria-labelledby="advanced-filter-title" aria-modal="true" className="advanced-filter-dialog" ref={dialogRef} role="dialog">
            <header><div><p>Filters</p><h2 id="advanced-filter-title">Find the right restaurant</h2></div><button aria-label="Close filters" onClick={() => setShowMore(false)}>×</button></header>
            <div className="advanced-filter-fields">
              <label>Cuisine<select onChange={(event) => setDraftFilters({ ...draftFilters, cuisine: event.target.value })} value={draftFilters.cuisine}><option value="">Any cuisine</option>{CUISINE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>Minimum rating<select onChange={(event) => setDraftFilters({ ...draftFilters, minimumRating: Number(event.target.value) })} value={draftFilters.minimumRating}><option value="0">Any rating</option><option value="4">4.0+</option><option value="4.5">4.5+</option></select></label>
              <label>Maximum distance<select onChange={(event) => setDraftFilters({ ...draftFilters, maximumDistanceKm: Number(event.target.value) })} value={draftFilters.maximumDistanceKm}><option value="2">2 km</option><option value="5">5 km</option><option value="10">10 km</option><option value="20">Any in map area</option></select></label>
              <label>Sort by<select onChange={(event) => setDraftFilters({ ...draftFilters, sort: event.target.value as AdvancedFilters["sort"] })} value={draftFilters.sort}><option value="relevance">Relevance</option><option value="rating">Rating</option><option value="distance">Distance</option><option value="price">Price</option></select></label>
            </div>
            <fieldset><legend>Price level</legend><div className="filter-checkbox-grid">{[0, 1, 2, 3, 4].map((level) => <label key={level}><input checked={draftFilters.priceLevels.includes(level)} onChange={(event) => setDraftFilters({ ...draftFilters, priceLevels: event.target.checked ? [...draftFilters.priceLevels, level] : draftFilters.priceLevels.filter((item) => item !== level) })} type="checkbox" />{level === 0 ? "Free" : "$".repeat(level)}</label>)}</div><small>Google price categories, not exact meal prices. Unknown price is excluded. Selecting price levels replaces Budget-friendly.</small></fieldset>
            <fieldset><legend>Google service attributes</legend><div className="filter-checkbox-grid">{[["takeout", "Takeout", "takeout"], ["delivery", "Delivery", "delivery"], ["reservations", "Reservations", "reservable"], ["accessibility", "Accessible entrance", "wheelchair_accessible_entrance"]].map(([key, label, field]) => <label key={key}><input checked={draftFilters[key as keyof AdvancedFilters] === true} onChange={(event) => setDraftFilters({ ...draftFilters, [key]: event.target.checked })} type="checkbox" />{label} ({filterDataPlaces.filter((place) => place[field as keyof Suggestion] === true).length} yes; {filterDataPlaces.filter((place) => typeof place[field as keyof Suggestion] !== "boolean").length} unknown)</label>)}</div><small>Only explicit Google yes values qualify. Accessible entrance does not imply full venue accessibility. Use Restaurant data to check more places.</small></fieldset>
            <fieldset><legend>Dietary options</legend><div className="filter-checkbox-grid">{["vegetarian", "vegan", "gluten-free", "halal"].map((item) => <label key={item}><input checked={draftFilters.dietary.includes(item)} onChange={(event) => setDraftFilters({ ...draftFilters, dietary: event.target.checked ? [...draftFilters.dietary, item] : draftFilters.dietary.filter((entry) => entry !== item) })} type="checkbox" />{item}</label>)}</div><small>Google categories or vegetarian offerings qualify. Menu inference requires explicit evidence for a complete dish; combined selections must share supporting evidence. Limited coverage, no certification or allergen safety guarantee.</small></fieldset>
            <label className="menu-label-toggle"><input checked={draftFilters.includeMenuLabels} onChange={(event) => setDraftFilters({ ...draftFilters, includeMenuLabels: event.target.checked })} type="checkbox" />Include labels inferred from official menus</label>
            <footer><button onClick={() => setDraftFilters({ ...DEFAULT_ADVANCED_FILTERS })}>Reset advanced filters</button><button className="primary-action" onClick={() => { onAdvancedFiltersChange(draftFilters); setShowMore(false); }}>Show results</button></footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
