import { useEffect, useRef, useState } from "react";
import { fetchDiscoveryNews, type DiscoveryNews } from "../api/discovery";
import { resolvePlaces } from "../api/product";
import type { Suggestion } from "../api/places";
import type { Coordinates } from "../types/searchArea";
import { PinIcon } from "./Icons";
import { RestaurantPhotos } from "./RestaurantPhotos";

function dateLabel(value: string): string {
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00Z` : value);
  return Number.isFinite(parsed.getTime()) ? parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "Date unavailable";
}

const LABELS = { newly_opened: "Newly opened", trending: "Trending in coverage", recently_spotted: "Recently spotted" };

export function NewsDiscoveries({ area, onShowOnMap }: {
  area: Coordinates | null;
  onShowOnMap: (place: Suggestion) => void;
}): JSX.Element {
  const [data, setData] = useState<DiscoveryNews | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [locating, setLocating] = useState<string | null>(null);
  const [locateError, setLocateError] = useState<{ id: string; message: string } | null>(null);
  const locateRequest = useRef<AbortController | null>(null);
  const lat = area?.lat; const lng = area?.lng;

  useEffect(() => {
    setData(null); setError(null); setLocateError(null); setLocating(null);
    locateRequest.current?.abort();
    if (lat === undefined || lng === undefined) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const news = await fetchDiscoveryNews({ lat, lng }, controller.signal);
        if (controller.signal.aborted) return;
        setData(news); setError(null);
        // Never keep an expired badge visible while waiting for its replacement.
        const expiry = news.expires_at ? Date.parse(news.expires_at) : NaN;
        const delay = Number.isFinite(expiry) ? Math.min(300000, Math.max(1000, expiry - Date.now())) : 300000;
        timer = setTimeout(() => {
          if (Number.isFinite(expiry) && expiry <= Date.now()) {
            setData(null); locateRequest.current?.abort(); setLocating(null);
          }
          void load();
        }, delay);
      } catch (reason) {
        if (!controller.signal.aborted) { setData(null); setError(reason instanceof Error ? reason.message : "Restaurant news could not be loaded."); }
      }
    };
    void load();
    return () => { controller.abort(); clearTimeout(timer); locateRequest.current?.abort(); };
  }, [lat, lng, retry]);

  async function locate(id: string): Promise<void> {
    locateRequest.current?.abort();
    const controller = new AbortController();
    locateRequest.current = controller;
    setLocating(id); setLocateError(null);
    try {
      const places = await resolvePlaces([id], controller.signal);
      if (controller.signal.aborted) return;
      const place = places.find((item) => item.place_id === id && Number.isFinite(item.lat) && Number.isFinite(item.lng));
      if (!place) throw new Error("This restaurant’s map details are unavailable. You can still open Google Maps.");
      onShowOnMap(place);
    } catch (reason) {
      if (!controller.signal.aborted) setLocateError({ id, message: reason instanceof Error ? reason.message : "Map details could not be loaded." });
    } finally {
      if (!controller.signal.aborted) setLocating(null);
    }
  }

  const unexpired = data?.expires_at && Date.parse(data.expires_at) > Date.now();
  const items = unexpired && (data.status === "ready" || data.status === "partial") ? data.items.filter((item) => Date.parse(item.expires_at) > Date.now()) : [];
  let notice = "Confirm a search area to explore restaurant news.";
  if (area && !data && !error) notice = "Checking restaurant news…";
  if (data?.status === "unsupported") notice = `News coverage currently includes ${data.coverage.join(", ")}. There are no regional news picks for this area yet.`;
  else if (data?.status === "pending") notice = "Regional news picks are not available yet. Nearby restaurants are available below.";
  else if (data?.status === "stale" || data?.status === "unavailable" || (data && !unexpired)) notice = "News updates are unavailable right now. Older picks are hidden until sources can be checked again.";
  else if (data && !items.length) notice = "No fresh, verified restaurant news picks for this region yet.";

  return <section className="news-discoveries" aria-labelledby="news-discoveries-title">
    <header><div><p>On the food radar{data?.region ? ` · ${data.region}` : ""}</p><h2 id="news-discoveries-title">New places. New reasons to go.</h2></div>
      <a href="https://gdeltproject.org/" target="_blank" rel="noreferrer">News metadata: GDELT Project</a></header>
    <p className="news-discoveries-intro">Regional news picks, with links to their sources. Map filters apply to the nearby restaurant collection below.</p>
    {items.length ? <>
      <div className="news-discovery-grid">{items.map((item) => <article className="news-discovery-card" key={item.place_id}>
        <div className="news-discovery-photo"><RestaurantPhotos placeId={item.place_id} title={item.name} /></div>
        <span className={`news-discovery-label is-${item.label}`}>{LABELS[item.label]}</span>
        <h3>{item.name}</h3><p>{item.address || item.city}</p>
        <p className="news-discovery-reason">{item.label === "newly_opened" && item.opening_date ? `Opening reported ${dateLabel(item.opening_date)}` : item.label === "trending" ? `${item.publisher_count} independent publisher groups in the past 14 days` : "A recent source mention; opening date unconfirmed"}</p>
        <ul>{item.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.publisher}</a><span>{source.published_at ? "Published" : "First indexed"} {dateLabel(source.published_at || source.observed_at)}</span><q>{source.evidence}</q></li>)}</ul>
        <div className="news-discovery-actions"><button type="button" aria-label={`${locating === item.place_id ? "Locating" : "Show on map"} ${item.name}`} disabled={locating !== null} onClick={() => void locate(item.place_id)}><PinIcon />{locating === item.place_id ? "Locating…" : "Show on map"}</button>
          <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(item.name)}&query_place_id=${encodeURIComponent(item.place_id)}`} target="_blank" rel="noreferrer">Google Maps</a></div>
        {locateError?.id === item.place_id ? <p role="alert">{locateError.message}</p> : null}
      </article>)}</div>
      <p className="news-discoveries-freshness">Sources checked {data?.checked_at ? dateLabel(data.checked_at) : "recently"}.{data?.status === "partial" ? " Coverage is limited while more headlines are checked." : ""} Trending measures coverage, not visits, ratings or demand.</p>
    </> : <p role="status">{error || notice}{error ? <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry news</button> : null}</p>}
    <details className="news-discovery-criteria"><summary>How these picks qualify</summary><p>Newly opened requires a source-reported opening date within 60 days. Trending requires distinct coverage from at least two known independent publisher groups within 14 days; duplicate or syndicated headlines do not add votes. Recently spotted means recent coverage, with no confirmed opening date. Index dates and publication dates are shown separately. A source check expires after 24 hours.</p></details>
  </section>;
}
