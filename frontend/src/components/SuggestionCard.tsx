import { useEffect, useState } from "react";

import { addFavorite } from "../api/favorites";
import { useAuth } from "../context/AuthContext";
import { useGoogleMaps } from "../context/GoogleMapsContext";
import { BookmarkIcon, PinIcon } from "./Icons";

type SuggestionCardProps = {
  placeId: string;
  title: string;
  description: string;
  tags?: string[];
  distance?: string;
  rating?: number;
};

type PhotoData = {
  uri: string;
  sourceUri?: string;
  attribution?: {
    name: string;
    uri?: string;
  };
};

export function SuggestionCard({
  placeId,
  title,
  description,
  tags = [],
  distance,
  rating,
}: SuggestionCardProps): JSX.Element {
  const { user } = useAuth();
  const { isLoaded } = useGoogleMaps();
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [photo, setPhoto] = useState<PhotoData | null>(null);
  const [photoUnavailable, setPhotoUnavailable] = useState(false);

  useEffect(() => {
    if (!isLoaded || !placeId || placeId.startsWith("placeholder-")) {
      setPhotoUnavailable(true);
      return;
    }
    let active = true;
    setPhoto(null);
    setPhotoUnavailable(false);

    const loadPhoto = async () => {
      try {
        const { Place } = (await google.maps.importLibrary(
          "places",
        )) as google.maps.PlacesLibrary;
        const place = new Place({ id: placeId });
        await place.fetchFields({ fields: ["photos"] });
        const firstPhoto = place.photos?.[0];
        if (!firstPhoto) {
          if (active) setPhotoUnavailable(true);
          return;
        }
        const firstAttribution = firstPhoto.authorAttributions?.[0];
        if (active) {
          setPhoto({
            uri: firstPhoto.getURI({ maxHeight: 280, maxWidth: 320 }),
            sourceUri: firstPhoto.googleMapsURI || undefined,
            attribution: firstAttribution
              ? {
                  name: firstAttribution.displayName,
                  uri: firstAttribution.uri || undefined,
                }
              : undefined,
          });
        }
      } catch {
        if (active) setPhotoUnavailable(true);
      }
    };
    void loadPhoto();
    return () => {
      active = false;
    };
  }, [isLoaded, placeId]);

  async function save(): Promise<void> {
    try {
      await addFavorite(title);
      setSaved(true);
      setSaveError(null);
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "Unable to save.");
    }
  }

  return (
    <article className="suggestion-card">
      <div className="suggestion-photo">
        {photo ? (
          <img
            alt={`Google Maps photo of ${title}`}
            loading="lazy"
            onError={() => {
              setPhoto(null);
              setPhotoUnavailable(true);
            }}
            src={photo.uri}
          />
        ) : (
          <div
            aria-label={photoUnavailable ? `No photo available for ${title}` : `Loading photo for ${title}`}
            className="suggestion-photo-fallback"
            role="img"
          >
            <img alt="" src="/craveai-pin.svg" />
          </div>
        )}
        {photo?.attribution ? (
          <a
            className="photo-attribution"
            href={photo.attribution.uri || photo.sourceUri}
            rel="noreferrer"
            target="_blank"
          >
            Photo: {photo.attribution.name}
          </a>
        ) : photo?.sourceUri ? (
          <a
            className="photo-attribution"
            href={photo.sourceUri}
            rel="noreferrer"
            target="_blank"
          >
            Google Maps photo
          </a>
        ) : null}
      </div>

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
