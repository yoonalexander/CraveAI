import { useEffect, useRef, useState } from "react";
import { CUISINE_OPTIONS } from "../utils/suggestionPool";
import { CuisineIcon } from "./CuisineIcon";

export function CuisineFilters({ cuisine, disabled, onChange }: {
  cuisine: string;
  disabled: boolean;
  onChange: (cuisine: string) => void;
}): JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    let wheelTarget: number | null = null;
    const resetWheelTarget = () => { wheelTarget = null; };
    const updateEdges = () => {
      const left = scroll.scrollLeft > 1;
      const right = scroll.scrollLeft + scroll.clientWidth < scroll.scrollWidth - 1;
      setEdges((current) => current.left === left && current.right === right ? current : { left, right });
    };
    const scrollWithWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.shiftKey || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) {
        resetWheelTarget();
        return;
      }
      const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 :
        event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? scroll.clientWidth : 1;
      const next = Math.max(0, Math.min(
        (wheelTarget ?? scroll.scrollLeft) + event.deltaY * unit,
        scroll.scrollWidth - scroll.clientWidth,
      ));
      if (next === scroll.scrollLeft && wheelTarget === null) return;
      event.preventDefault();
      wheelTarget = next;
      scroll.scrollTo({
        left: next,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      });
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateEdges);
    observer?.observe(scroll);
    for (const child of scroll.children) observer?.observe(child);
    scroll.addEventListener("scroll", updateEdges, { passive: true });
    scroll.addEventListener("wheel", scrollWithWheel, { passive: false });
    scroll.addEventListener("scrollend", resetWheelTarget);
    scroll.addEventListener("pointerdown", resetWheelTarget);
    scroll.addEventListener("keydown", resetWheelTarget);
    updateEdges();
    return () => {
      observer?.disconnect();
      scroll.removeEventListener("scroll", updateEdges);
      scroll.removeEventListener("wheel", scrollWithWheel);
      scroll.removeEventListener("scrollend", resetWheelTarget);
      scroll.removeEventListener("pointerdown", resetWheelTarget);
      scroll.removeEventListener("keydown", resetWheelTarget);
    };
  }, []);

  return <div className={`cuisine-filters${edges.left ? " can-scroll-left" : ""}${edges.right ? " can-scroll-right" : ""}`}>
    <div className="cuisine-filter-scroll" ref={scrollRef} role="group" aria-label="Cuisine filters">
      {["", ...CUISINE_OPTIONS].map((choice) => <button key={choice} type="button"
        aria-pressed={cuisine === choice} disabled={disabled} onClick={() => onChange(choice)}>
        <CuisineIcon cuisine={choice} /><span>{choice || "Any cuisine"}</span>
        <span className="cuisine-choice-check" aria-hidden="true">{cuisine === choice ? "✓" : ""}</span>
      </button>)}
    </div>
  </div>;
}
