import { useEffect, useState } from "react";

import { addFavorite, listSavedPlaces } from "../api/favorites";
import { useAuth } from "../context/AuthContext";
import { RestaurantPhotos } from "./RestaurantPhotos";
import { BookmarkIcon, PinIcon } from "./Icons";
import { FilterEvidence } from "./FilterEvidence";
import type { FilterLabel } from "../api/places";

type SuggestionCardProps = {
  placeId: string;
  title: string;
  description: string;
  tags?: string[];
  distance?: string;
  rating?: number | null;
  filterLabels?: FilterLabel[];
  compactPhoto?: boolean;
};

let savedPlaceIdsPromise: Promise<Set<string>> | null = null;

function loadSavedPlaceIds(): Promise<Set<string>> {
  if (!savedPlaceIdsPromise) {
    savedPlaceIdsPromise = listSavedPlaces().then(
      (items) => new Set(items.flatMap((item) => item.place_id ? [item.place_id] : [])),
      () => new Set(),
    );
  }
  return savedPlaceIdsPromise;
}

export function SuggestionCard({
  placeId,
  title,
  description,
  tags = [],
  distance,
  rating,
  filterLabels,
  compactPhoto = false,
}: SuggestionCardProps): JSX.Element {
  const { user } = useAuth();
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      setSaved(false);
      return;
    }
    let active = true;
    loadSavedPlaceIds().then((ids) => {
      if (active) setSaved(ids.has(placeId));
    });
    return () => { active = false; };
  }, [placeId, user]);

  useEffect(() => {
    const refresh = () => {
      savedPlaceIdsPromise = null;
      if (user) void loadSavedPlaceIds().then((ids) => setSaved(ids.has(placeId)));
    };
    window.addEventListener("craveai-favorites-changed", refresh);
    return () => window.removeEventListener("craveai-favorites-changed", refresh);
  }, [placeId, user]);

  async function save(): Promise<void> {
    try {
      await addFavorite(placeId);
      setSaved(true);
      savedPlaceIdsPromise = Promise.resolve(new Set([
        ...Array.from(await loadSavedPlaceIds()),
        placeId,
      ]));
      window.dispatchEvent(new Event("craveai-favorites-changed"));
      setSaveError(null);
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "Unable to save.");
    }
  }

  return (
    <article className="suggestion-card">
      <div className="suggestion-photo"><RestaurantPhotos placeId={placeId} title={title} compact={compactPhoto} /></div>

      <div className="suggestion-card-body">
        <div className="suggestion-card-heading">
          <h3>{title}</h3>
          {typeof rating === "number" ? (
            <span aria-label={`${rating.toFixed(1)} out of 5 stars`}>
              ★ {rating.toFixed(1)}
            </span>
          ) : null}
        </div>
        <p className="suggestion-address">{description}</p>
        <FilterEvidence labels={filterLabels} />
        {!placeId.startsWith("placeholder-") ? (
          <a
            className="suggestion-google-source"
            href={`https://www.google.com/maps/search/?api=1&query_place_id=${encodeURIComponent(placeId)}`}
            rel="noreferrer"
            target="_blank"
          >
            View on Google Maps
          </a>
        ) : null}
        <div className="suggestion-card-footer">
          <div className="suggestion-meta">
            {tags.slice(0, 1).map((tag) => <span key={tag}>{tag}</span>)}
            {distance ? <span><PinIcon /> {distance}</span> : null}
          </div>

          <div className="suggestion-save-row">
            {user ? (
              <button disabled={saved} onClick={() => void save()} type="button">
                {saved ? "Saved" : "Save"}
              </button>
            ) : (
              <a href="/login">Sign in to save</a>
            )}
            <button
              aria-label={saved ? `${title} saved` : `Save ${title}`}
              className="bookmark-button"
              disabled={!user || saved}
              onClick={() => void save()}
              title={user ? "Save restaurant" : "Sign in to save"}
              type="button"
            >
              <BookmarkIcon />
            </button>
          </div>
        </div>
        {saveError ? <p className="suggestion-save-error" role="alert">{saveError}</p> : null}
      </div>
    </article>
  );
}
