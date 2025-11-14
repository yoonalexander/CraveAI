import { useMemo } from "react";
import { GoogleMap, Marker, useJsApiLoader } from "@react-google-maps/api";

import { ChatRecommendation } from "../api/chat";

type MapViewProps = {
  userLocation: { lat: number; lng: number };
  recommendations: ChatRecommendation[];
  hasLiveLocation: boolean;
  statusMessage: string;
};

const emptyStateClass =
  "flex h-full items-center justify-center px-6 text-center text-sm text-slate-400";

export function MapView({
  userLocation,
  recommendations,
  hasLiveLocation,
  statusMessage,
}: MapViewProps): JSX.Element {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.toString()?.trim();
  const markers = useMemo(
    () =>
      recommendations.filter(
        (place) => typeof place.lat === "number" && typeof place.lng === "number",
      ),
    [recommendations],
  );

  const subtitle = hasLiveLocation
    ? "Locked on to your current location."
    : "Using Hamilton, ON fallback.";

  if (!apiKey) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-slate-900/40">
        <div className="border-b border-slate-800 px-5 py-4">
          <h3 className="text-base font-semibold text-white">Nearby Map</h3>
          <p className="text-sm text-slate-400">
            Add <code className="text-primary">VITE_GOOGLE_MAPS_API_KEY</code> to enable the map.
          </p>
        </div>
        <div className={emptyStateClass}>
          Map rendering is disabled until a Google Maps key is provided.
        </div>
      </div>
    );
  }

  const { isLoaded, loadError } = useJsApiLoader({
    id: "craveai-map",
    googleMapsApiKey: apiKey,
  });

  const mapCenter = userLocation;
  const mapZoom = hasLiveLocation ? 13 : 12;

  let mapContent: JSX.Element;
  if (loadError) {
    mapContent = (
      <div className={emptyStateClass}>
        Failed to load Google Maps ({loadError.message}). Check your quota and try again.
      </div>
    );
  } else if (!isLoaded) {
    mapContent = <div className={emptyStateClass}>Loading live map\u2026</div>;
  } else {
    mapContent = (
      <GoogleMap
        mapContainerStyle={{ width: "100%", height: "100%" }}
        center={mapCenter}
        zoom={mapZoom}
        options={{
          disableDefaultUI: true,
          styles: [
            {
              elementType: "geometry",
              stylers: [{ color: "#0f172a" }],
            },
            {
              elementType: "labels.icon",
              stylers: [{ visibility: "off" }],
            },
            {
              elementType: "labels.text.fill",
              stylers: [{ color: "#94a3b8" }],
            },
            {
              elementType: "labels.text.stroke",
              stylers: [{ color: "#0f172a" }],
            },
          ],
        }}
      >
        <Marker
          position={userLocation}
          title={hasLiveLocation ? "You are here" : "Fallback location"}
          label="ME"
        />
        {markers.map((place, index) =>
          place.lat && place.lng ? (
            <Marker
              key={`${place.name}-${place.lat}-${place.lng}-${index}`}
              position={{ lat: place.lat, lng: place.lng }}
              label={`${index + 1}`}
              title={place.name}
            />
          ) : null,
        )}
      </GoogleMap>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/40">
      <div className="border-b border-slate-800 px-5 py-4">
        <p className="text-sm uppercase tracking-[0.25em] text-primary">Live Map</p>
        <h3 className="text-base font-semibold text-white">Restaurants Near You</h3>
        <p className="text-xs text-slate-400">
          {subtitle} {markers.length ? `Plotting ${markers.length} matches.` : "Waiting for a conversation to begin."}
        </p>
        <p className="mt-1 text-xs text-slate-500">{statusMessage}</p>
      </div>
      <div className="h-[320px] overflow-hidden rounded-b-3xl">{mapContent}</div>
    </div>
  );
}
