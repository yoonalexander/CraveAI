import { useEffect, useRef, useState } from "react";

import { useGoogleMaps } from "../context/GoogleMapsContext";
import { CloseIcon, PinIcon, SearchIcon } from "./Icons";

export type SelectedLocation = {
  lat: number;
  lng: number;
  label: string;
  source: "device" | "manual";
};

type LocationDialogProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (location: SelectedLocation) => void;
};

export function LocationDialog({
  open,
  onClose,
  onSelect,
}: LocationDialogProps): JSX.Element | null {
  const { isLoaded, hasApiKey } = useGoogleMaps();
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [candidate, setCandidate] = useState<SelectedLocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    if (!open || !isLoaded || !inputRef.current) return;
    const autocomplete = new google.maps.places.Autocomplete(inputRef.current, {
      fields: ["address_components", "formatted_address", "geometry", "name"],
      types: ["geocode", "establishment"],
    });
    const listener = autocomplete.addListener("place_changed", () => {
      const place = autocomplete.getPlace();
      const location = place.geometry?.location;
      if (!location) {
        setCandidate(null);
        setError("Choose a location from the suggestions.");
        return;
      }
      setCandidate({
        lat: location.lat(),
        lng: location.lng(),
        label: place.name || place.formatted_address || "Selected location",
        source: "manual",
      });
      setError(null);
    });
    return () => listener.remove();
  }, [isLoaded, open]);

  useEffect(() => {
    if (!open) return;
    document.body.classList.add("crave-overlay-open");
    setCandidate(null);
    setError(null);
    window.setTimeout(() => inputRef.current?.focus(), 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("crave-overlay-open");
    };
  }, [onClose, open]);

  if (!open) return null;

  const useDeviceLocation = () => {
    if (!("geolocation" in navigator)) {
      setError("This browser cannot access your current location.");
      return;
    }
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        onSelect({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          label: "Current location",
          source: "device",
        });
      },
      () => {
        setLocating(false);
        setError("We couldn't access your current location. Check your browser permission.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        aria-describedby="location-description"
        aria-labelledby="location-title"
        aria-modal="true"
        className="location-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        ref={dialogRef}
        role="dialog"
      >
        <button
          aria-label="Close location dialog"
          className="dialog-close"
          onClick={onClose}
          type="button"
        >
          <CloseIcon />
        </button>
        <div className="dialog-icon"><PinIcon /></div>
        <h2 id="location-title">Change your location</h2>
        <p id="location-description">
          Search for an address or use your device location to refresh nearby spots.
        </p>

        <label className="location-search-label" htmlFor="location-search">
          Search for a place
        </label>
        <div className="location-search-field">
          <SearchIcon />
          <input
            disabled={!hasApiKey || !isLoaded}
            id="location-search"
            onChange={() => {
              setCandidate(null);
              setError(null);
            }}
            placeholder={hasApiKey ? "Enter a city, neighbourhood, or address" : "Google Maps key required"}
            ref={inputRef}
          />
        </div>

        <button
          className="device-location-button"
          disabled={locating}
          onClick={useDeviceLocation}
          type="button"
        >
          <PinIcon />
          {locating ? "Finding your location…" : "Use my current location"}
        </button>

        {error ? <p className="dialog-error" role="alert">{error}</p> : null}
        {!hasApiKey ? (
          <p className="dialog-note">Address search is unavailable until the browser Google Maps key is configured.</p>
        ) : null}

        <div className="dialog-actions">
          <button className="dialog-cancel" onClick={onClose} type="button">Cancel</button>
          <button
            className="dialog-primary"
            disabled={!candidate}
            onClick={() => candidate && onSelect(candidate)}
            type="button"
          >
            Use this location
          </button>
        </div>
      </div>
    </div>
  );
}
