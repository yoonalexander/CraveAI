import type { ReactNode } from "react";

// Original CraveAI SVG drawings. Dishes are visual cues, not menu or dietary claims.
// Shared dishes deliberately reuse artwork; every control retains its cuisine name.
const dishes: Record<string, ReactNode> = {
  plate: <><circle cx="14" cy="14" r="8" className="food-cream" /><circle cx="14" cy="14" r="5" /><path d="M2 4v7m3-7v7M2 8h3m-1.5 3v13M25 4v20m0-20c-3 2-3 8 0 9" /></>,
  burger: <><path d="M4 11c0-10 20-10 20 0Z" className="food-gold" /><path d="M4 20h20v2c0 3-20 3-20 0Z" className="food-gold" /><path d="m3 14 4 2 4-2 4 2 4-2 6 2" className="food-leaf" /><rect x="3" y="17" width="22" height="3" rx="1.5" className="food-red" /><path d="m9 7 .5.5m5-2 .5.5m4 2 .5.5" /></>,
  skewers: <><path d="m5 24 16-20m-8 21L26 8" /><path d="m7 17 4 3 5-6-4-3Zm7-9 4 3 5-6-4-3Z" className="food-gold" /><path d="m16 17 4 3 4-5-4-3Z" className="food-red" /><path d="m6 20 3 2m13-13 3 2" className="food-leaf" /></>,
  dumpling: <><path d="M3 19c0-17 22-17 22 0-4 7-18 7-22 0Z" className="food-cream" /><path d="m4 15 4 3 2-6 4 4 4-4 2 6 4-3" /><path d="M6 22h16" /></>,
  croissant: <><path d="M3 9c1 1 3 2 5 1 0 8 12 8 12 0 2 1 4 0 5-1 2 7-3 15-11 15S1 16 3 9Z" className="food-gold" /><path d="m8 10 2 13m10-13-2 13M4 15l4 3m16-3-4 3M14 16v8" /></>,
  salad: <><path d="M3 14h22c-1 12-21 12-22 0Z" className="food-cream" /><path d="M6 14c-6-8 3-13 8-6 4-8 13-2 8 6Z" className="food-leaf" /><circle cx="10" cy="11" r="2.5" className="food-red" /><rect x="16" y="9" width="4" height="4" rx=".5" className="food-cream" /><path d="M9 20h10" /></>,
  curry: <><path d="M4 13h20v6c0 7-20 7-20 0Z" className="food-red" /><ellipse cx="14" cy="13" rx="10" ry="4" className="food-gold" /><path d="M9 13h1m4-1h1m3 2h1M8 7c-2-2 2-2 0-4m6 4c-2-2 2-2 0-4m6 4c-2-2 2-2 0-4" /></>,
  pasta: <><ellipse cx="14" cy="19" rx="11" ry="6" className="food-cream" /><path d="M8 18c-3-9 4-10 5-5s-7 2-3 7m5-1c-3-9 4-10 5-5s-7 2-3 7M7 21h14" className="food-gold" /><path d="M13 11c-1-6 5-6 7-6-1 4-4 6-7 6Z" className="food-leaf" /></>,
  sushi: <><rect x="3" y="12" width="14" height="11" rx="5" className="food-leaf" /><ellipse cx="10" cy="12" rx="7" ry="4" className="food-cream" /><ellipse cx="10" cy="12" rx="3" ry="2" className="food-red" /><path d="M18 18h6v5h-6" className="food-cream" /><path d="M17 16c0-4 8-4 8 0v2h-8Z" className="food-red" /><path d="m5 3 19 7M9 2l16 4" /></>,
  rice: <><path d="M3 14h22c-1 12-21 12-22 0Z" className="food-cream" /><path d="M5 14c0-10 18-10 18 0" className="food-leaf" /><path d="m6 9 5 5m9-5-4 5" className="food-red" /><ellipse cx="14" cy="9" rx="5" ry="4" className="food-cream" /><circle cx="14" cy="9" r="2" className="food-gold" /></>,
  mezze: <><ellipse cx="14" cy="17" rx="11" ry="8" className="food-cream" /><circle cx="12" cy="17" r="5" className="food-gold" /><path d="M10 16c4-3 6 3 2 4m7-5 3 4m-4 2 3 1" /><path d="M4 11 8 3l6 4-4 5" className="food-gold" /><path d="M20 9c0-4 4-4 5-3-1 4-3 5-5 3Z" className="food-leaf" /></>,
  olives: <><ellipse cx="14" cy="19" rx="11" ry="6" className="food-cream" /><ellipse cx="9" cy="18" rx="3" ry="4" className="food-leaf" /><ellipse cx="17" cy="20" rx="4" ry="3" className="food-leaf" /><path d="M13 17 19 4m-2 5c-6-5-7-1-4 1m4 0c6 0 7-4 3-5" className="food-leaf" /></>,
  taco: <><path d="M4 20C0 4 23 0 25 20Z" className="food-gold" /><path d="m5 13 3-4 3 2 3-4 3 3 4-1 3 6" className="food-leaf" /><path d="M4 20c0-14 18-14 18 0Z" className="food-gold" /><path d="m8 16 .5.5m5-3 .5.5m4 4 .5.5" /><circle cx="19" cy="10" r="2" className="food-red" /></>,
  paella: <><path d="M2 16h3m18 0h3M4 14h20v5c0 7-20 7-20 0Z" className="food-red" /><ellipse cx="14" cy="14" rx="10" ry="5" className="food-gold" /><path d="m8 12 2 3m8-4-2 5m-5-6 2 2m4 5h3" /><circle cx="7" cy="15" r="1.2" className="food-leaf" /><circle cx="20" cy="13" r="1.2" className="food-leaf" /></>,
  noodles: <><path d="M3 15h22c-1 12-21 12-22 0Z" className="food-cream" /><path d="M7 15V9c0-4 4-4 4 0v6m3 0V9c0-4 4-4 4 0v6m3 0v-5" className="food-gold" /><path d="M4 4 23 7M7 2l17 2" /><path d="m6 19 3 2m10-3-3 4" className="food-leaf" /></>,
  soup: <><path d="M3 14h22c-1 13-21 13-22 0Z" className="food-cream" /><ellipse cx="14" cy="14" rx="11" ry="4" className="food-gold" /><path d="M7 14c2-4 4 4 6 0s4 4 6 0M9 7c-2-2 2-2 0-4m6 4c-2-2 2-2 0-4" /><path d="M18 12c0-4 5-5 7-3-2 4-5 5-7 3Z" className="food-leaf" /></>,
};

const cuisineDishes: Record<string, string> = {
  american: "burger", brazilian: "skewers", chinese: "dumpling", french: "croissant",
  greek: "salad", indian: "curry", indonesian: "skewers", italian: "pasta",
  japanese: "sushi", korean: "rice", lebanese: "mezze", mediterranean: "olives",
  mexican: "taco", "middle eastern": "mezze", spanish: "paella", thai: "noodles",
  turkish: "skewers", vietnamese: "soup",
};

export function CuisineIcon({ cuisine, className = "" }: { cuisine?: string; className?: string }): JSX.Element {
  const key = cuisine?.trim().toLowerCase() || "";
  const dish = Object.prototype.hasOwnProperty.call(cuisineDishes, key) ? cuisineDishes[key] : "plate";
  return <svg aria-hidden="true" focusable="false" className={`cuisine-icon ${className}`.trim()} data-food-icon={dish}
    viewBox="0 0 28 28" fill="none" stroke="var(--food-ink, #594535)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {dishes[dish]}
  </svg>;
}
