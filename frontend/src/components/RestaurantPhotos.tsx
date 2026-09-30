import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { fetchPlacePhoto, PhotoLimitError, type PlacePhoto } from "../api/photos";

// Key the entire session by venue: old images, requests and gallery indexes cannot
// survive a map selection change. Provider data stays in component memory only.
type PhotoProps = { placeId?: string | null; title: string; compact?: boolean };
export function RestaurantPhotos({ placeId, title, compact = false }: PhotoProps): JSX.Element {
  return <PhotoSession key={placeId || "missing"} placeId={placeId} title={title} compact={compact} />;
}

function PhotoSession({ placeId, title, compact }: PhotoProps): JSX.Element {
  const container = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [data, setData] = useState<PlacePhoto | null>(null);
  const [index, setIndex] = useState(0);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const validId = Boolean(placeId && /^[A-Za-z0-9_-]{1,256}$/.test(placeId) && !placeId.startsWith("placeholder-"));

  useEffect(() => {
    if (!validId || !container.current) return;
    if (typeof IntersectionObserver === "undefined") { setVisible(true); return; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setVisible(true); observer.disconnect(); }
    }, { rootMargin: "100px" });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [validId]);

  useEffect(() => {
    if (!visible || !validId || !placeId) return;
    const controller = new AbortController();
    setLoading(true); setError(null); setLimited(false); setImageFailed(false);
    void fetchPlacePhoto(placeId, index, controller.signal).then((result) => {
      if (!controller.signal.aborted) setData(result);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setError(reason instanceof PhotoLimitError ? reason.message : "Photos could not be loaded.");
      setLimited(reason instanceof PhotoLimitError);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [placeId, validId, visible, index, retry]);

  const photo = data?.photo;
  const unavailable = !validId || Boolean(data && !photo);
  const photoVisible = photo && !loading && !error && !imageFailed;
  function image(): JSX.Element {
    return photoVisible ? <img className="restaurant-photo-image" alt={`Google Maps photo of ${title}`} src={photo.uri} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setImageFailed(true)} /> : (
      <div className="restaurant-photo-fallback" role="img" aria-label={unavailable || error || imageFailed ? `No photo available for ${title}` : `Loading photo for ${title}`}>
        <img alt="" src="/craveai-pin.svg" />
        <p>{loading ? "Loading photo…" : error || (imageFailed ? "This photo could not be loaded." : unavailable ? "No photos available yet" : "Restaurant photos")}</p>
        {(error || imageFailed) && !limited ? <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry photos</button> : null}
      </div>
    );
  }
  function credits(full = !compact): JSX.Element | null {
    if (!photoVisible) return null;
    return <figcaption className="restaurant-photo-credits">
      <a className="google-maps-credit" translate="no" href={photo.source_uri || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(title)}&query_place_id=${encodeURIComponent(placeId || "")}`} target="_blank" rel="noreferrer">Google Maps</a>
      {full ? photo.authors.map((author, i) => <div className="photo-contributor" key={`${author.name}-${i}`}>
        {author.avatar_uri ? <img alt="" src={author.avatar_uri} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={(event) => { event.currentTarget.hidden = true; }} /> : null}
        {author.uri ? <a href={author.uri} target="_blank" rel="noreferrer">Photo: {author.name}</a> : <span>Photo: {author.name}</span>}
      </div>) : null}
      {full && photo.report_uri ? <a href={photo.report_uri} target="_blank" rel="noreferrer">Report photo</a> : null}
    </figcaption>;
  }
  return <figure ref={container} className="restaurant-photos" aria-label={`Photos of ${title}`}>
    <div className="restaurant-photo-frame">
      {image()}
      {photo ? <button className="photo-expand" aria-label={`View photos of ${title}`} type="button" onClick={() => setExpanded(true)}>⛶</button> : null}
    </div>
    {credits()}
    {expanded ? <PhotoDialog title={title} onClose={() => setExpanded(false)}>
      <figure className="restaurant-photos is-expanded">
        <div className="restaurant-photo-frame">{image()}</div>
        {credits(true)}
      </figure>
      <div className="photo-gallery-controls">
        <button type="button" aria-label="Previous photo" disabled={loading || limited || !data || data.index === 0} onClick={() => setIndex((data?.index || 0) - 1)}>←</button>
        <span role="status">{loading ? "Loading photo…" : data?.total ? `${data.index + 1} / ${data.total}` : "No photos available"}</span>
        <button type="button" aria-label="Next photo" disabled={loading || limited || !data || data.index >= data.total - 1} onClick={() => setIndex((data?.index || 0) + 1)}>→</button>
      </div>
    </PhotoDialog> : null}
  </figure>;
}

function PhotoDialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }): JSX.Element {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const backdrop = dialog.current?.parentElement;
    const backgrounds = Array.from(document.body.children).filter((element) => element !== backdrop) as HTMLElement[];
    const previousInert = backgrounds.map((element) => element.inert);
    backgrounds.forEach((element) => { element.inert = true; });
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    function keydown(event: KeyboardEvent): void {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (event.key !== "Tab") return;
      const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href]") || []);
      const first = elements[0], last = elements[elements.length - 1];
      if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); first?.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keydown, true);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      document.body.style.overflow = previousOverflow;
      backgrounds.forEach((element, i) => { element.inert = previousInert[i]; });
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  return createPortal(<div className="photo-dialog-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={dialog} className="photo-dialog" role="dialog" aria-modal="true" aria-label={`Photos of ${title}`}>
      <header><h2>{title}</h2><button type="button" aria-label="Close photos" onClick={onClose}>×</button></header>
      {children}
    </div>
  </div>, document.body);
}
