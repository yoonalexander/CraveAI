import { CUISINE_OPTIONS } from "../utils/suggestionPool";
import { CuisineIcon } from "./CuisineIcon";

export function CuisineFilters({ cuisine, disabled, onChange }: {
  cuisine: string;
  disabled: boolean;
  onChange: (cuisine: string) => void;
}): JSX.Element {
  return <div className="cuisine-filters">
    <div className="cuisine-filter-heading"><span>Cuisines</span><span>Scroll to explore</span></div>
    <div className="cuisine-filter-scroll" role="group" aria-label="Cuisine filters">
      {["", ...CUISINE_OPTIONS].map((choice) => <button key={choice} type="button"
        aria-pressed={cuisine === choice} disabled={disabled} onClick={() => onChange(choice)}>
        <CuisineIcon cuisine={choice} /><span>{choice || "Any cuisine"}</span>
        <span className="cuisine-choice-check" aria-hidden="true">{cuisine === choice ? "✓" : ""}</span>
      </button>)}
    </div>
  </div>;
}
