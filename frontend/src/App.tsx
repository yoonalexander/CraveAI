import { useMemo, useState, useEffect, useRef } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { SuggestionCard } from "./components/SuggestionCard";
import { MapView } from "./components/MapView";
import { ChatRecommendation } from "./api/chat";
import { ThemeProvider } from "./context/ThemeContext";
import { ThemeToggle } from "./components/ThemeToggle";
import { AccountMenu } from "./components/AccountMenu";
import {
  fetchSuggestions,
  PlacesQuotaError,
  Suggestion,
} from "./api/places";
import {
  calculateDistanceKm,
  getNextSuggestionIndex,
  getVisibleSuggestions,
  MATERIAL_LOCATION_CHANGE_KM,
} from "./utils/suggestionPool";

const SUGGESTION_ROTATION_MS = 30000;
// Render's free web services can take about a minute to wake after being idle.
// Keep this above that cold-start window so the browser does not abort a
// healthy suggestions request just before the backend becomes available.
const SUGGESTION_TIMEOUT_MS = 90000;

const HAMILTON_FALLBACK = {
  lat: 43.2557,
  lng: -79.8711,
  city: "Hamilton",
  radius: 5000,
};

type Coordinates = {
  lat: number;
  lng: number;
};

function App(): JSX.Element {
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null);
  const [locationStatus, setLocationStatus] = useState(
    "Calibrating your location\u2026",
  );
  const [locationReady, setLocationReady] = useState(false);
  const [mapRecommendations, setMapRecommendations] = useState<
    ChatRecommendation[]
  >([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionQuotaResetAt, setSuggestionQuotaResetAt] = useState<
    string | null
  >(null);
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [suggestionRetryVersion, setSuggestionRetryVersion] = useState(0);
  const lastSuggestionLocation = useRef<Coordinates | null>(null);
  const lastRetryVersion = useRef(-1);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setLocationStatus(
        "Geolocation not supported; using Hamilton, ON as a fallback.",
      );
      setLocationReady(true);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setLocationStatus("Live location locked. Refining searches nearby.");
        setLocationReady(true);
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setLocationStatus(
            "Location permission denied; relying on Hamilton, ON for now.",
          );
        } else {
          setLocationStatus(
            "Unable to read device location; using Hamilton, ON fallback.",
          );
        }
        setLocationReady(true);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      },
    );
  }, []);

  useEffect(() => {
    if (!locationReady) return;

    const loc = userLocation || HAMILTON_FALLBACK;
    const isManualRetry = suggestionRetryVersion !== lastRetryVersion.current;
    const previousLocation = lastSuggestionLocation.current;
    if (
      !isManualRetry &&
      previousLocation &&
      calculateDistanceKm(
        previousLocation.lat,
        previousLocation.lng,
        loc.lat,
        loc.lng,
      ) < MATERIAL_LOCATION_CHANGE_KM
    ) {
      return;
    }

    const controller = new AbortController();
    const fetchNearby = async () => {
      setIsLoadingSuggestions(true);
      setSuggestionError(null);
      setSuggestionQuotaResetAt(null);
      setSuggestions([]);
      setSuggestionIndex(0);

      const timeoutId = window.setTimeout(() => {
        controller.abort();
        setSuggestionError("We couldn't load suggestions in time.");
        setIsLoadingSuggestions(false);
      }, SUGGESTION_TIMEOUT_MS);

      try {
        const data = await fetchSuggestions(
          loc.lat,
          loc.lng,
          HAMILTON_FALLBACK.radius,
          controller.signal,
        );
        setSuggestions(data);
        setSuggestionIndex(0);
        lastSuggestionLocation.current = { lat: loc.lat, lng: loc.lng };
        lastRetryVersion.current = suggestionRetryVersion;
        if (data.length === 0) {
          setSuggestionError("No nearby restaurants were found.");
        }
      } catch (error) {
        if (controller.signal.aborted) return;

        console.error("Failed to fetch suggestions:", error);
        if (error instanceof PlacesQuotaError) {
          setSuggestionQuotaResetAt(error.resetAt);
          setSuggestionError(formatPlacesQuotaError(error.resetAt));
        } else {
          setSuggestionError("Failed to load suggestions.");
        }
      } finally {
        clearTimeout(timeoutId);
        if (!controller.signal.aborted) {
          setIsLoadingSuggestions(false);
        }
      }
    };

    fetchNearby();

    return () => {
      controller.abort();
    };
  }, [userLocation, locationReady, suggestionRetryVersion]);

  useEffect(() => {
    if (suggestions.length === 0) return;
    const interval = setInterval(() => {
      setSuggestionIndex((prev) =>
        getNextSuggestionIndex(prev, suggestions.length),
      );
    }, SUGGESTION_ROTATION_MS);
    return () => clearInterval(interval);
  }, [suggestions]);

  const visibleSuggestions = useMemo(() => {
    return getVisibleSuggestions(suggestions, suggestionIndex);
  }, [suggestions, suggestionIndex]);

  const chatLocation = useMemo(() => {
    if (userLocation) {
      return {
        ...userLocation,
        radius: 5000,
      };
    }
    return locationReady ? HAMILTON_FALLBACK : null;
  }, [userLocation, locationReady]);

  const mapLocation = userLocation
    ? {
        lat: userLocation.lat,
        lng: userLocation.lng,
      }
    : locationReady
      ? {
          lat: HAMILTON_FALLBACK.lat,
          lng: HAMILTON_FALLBACK.lng,
        }
      : null;

  return (
    <ThemeProvider defaultTheme="light" storageKey="craveai-theme">
      <div className="min-h-screen bg-background text-foreground transition-colors duration-300">
        <header className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 pb-10 pt-14 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <img
                src="/craveai-pin.svg"
                alt=""
                className="h-10 w-10 object-contain"
              />
              <p className="text-sm font-bold uppercase tracking-[0.32em] text-primary">
                craveai
              </p>
            </div>
            <h1 className="mt-2 text-4xl font-semibold md:text-5xl text-foreground">
              Find your next bite.
            </h1>
            <p className="mt-4 max-w-xl text-muted-foreground">
              A conversational guide that pairs your cravings, mood, and dietary
              needs with the best local spots. The chat experience is ready for
              wiring to the backend RAG pipeline next.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <AccountMenu />
          </div>
        </header>

        <main className="mx-auto grid w-full max-w-6xl gap-6 px-6 pb-16 md:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <section className="h-[600px] md:h-[720px]">
            <ChatPanel
              location={chatLocation}
              locationStatus={locationStatus}
              onRecommendations={setMapRecommendations}
              candidatePlaces={suggestions}
            />
          </section>
          <aside className="flex flex-col gap-4">
            <MapView
              userLocation={mapLocation}
              recommendations={mapRecommendations}
              hasLiveLocation={Boolean(userLocation)}
              isLocating={!locationReady}
              statusMessage={locationStatus}
            />
            <div className="rounded-3xl border border-border bg-secondary/40 p-5 text-foreground">
              <h2 className="text-lg font-semibold">
                Today&apos;s Suggested Spots
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Rotating through up to 20 top-rated spots near you, three at a
                time.
              </p>
              {isLoadingSuggestions && (
                <div className="mt-4 flex items-center gap-4 rounded-2xl bg-secondary/70 p-3 shadow-inner">
                  <div className="relative h-10 w-10 shrink-0">
                    <div className="absolute inset-0 rounded-full border-2 border-primary/25" />
                    <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  </div>
                  <div className="text-sm">
                    <p className="font-medium text-foreground">
                      {suggestionError
                        ? "Trying again..."
                        : "Finding nearby restaurants..."}
                    </p>
                    <p className="text-muted-foreground">
                      Using your location and Google Places. The first load may
                      take about a minute.
                    </p>
                  </div>
                </div>
              )}
              {suggestionError && !isLoadingSuggestions && (
                <div className="mt-4 rounded-2xl border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                  <p>{suggestionError}</p>
                  {!suggestionQuotaResetAt && (
                    <button
                      type="button"
                      className="mt-3 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground"
                      onClick={() =>
                        setSuggestionRetryVersion((version) => version + 1)
                      }
                    >
                      Try again
                    </button>
                  )}
                </div>
              )}
              {suggestions.length > 0 && (
                <p className="mt-3 text-right text-[10px] text-muted-foreground">
                  Powered by Google
                </p>
              )}
            </div>
            <div className="grid gap-4">
              {isLoadingSuggestions ? (
                <div className="space-y-4">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="h-32 animate-pulse rounded-3xl bg-secondary/50"
                    />
                  ))}
                </div>
              ) : visibleSuggestions.length > 0 ? (
                visibleSuggestions.map((suggestion) => (
                  <SuggestionCard
                    key={suggestion.place_id}
                    title={suggestion.name}
                    description={suggestion.reason || suggestion.address}
                    tags={suggestion.tags || []}
                    distance={
                      userLocation
                        ? `${calculateDistance(
                            userLocation.lat,
                            userLocation.lng,
                          suggestion.lat,
                          suggestion.lng,
                        ).toFixed(1)} km`
                        : ""
                    }
                    rating={suggestion.rating}
                  />
                ))
              ) : suggestionError ? (
                <div className="rounded-3xl border border-border bg-secondary/40 p-4 text-sm text-foreground shadow">
                  We&apos;re having trouble showing spots right now.
                </div>
              ) : (
                <div className="rounded-3xl border border-border bg-secondary/40 p-4 text-sm text-muted-foreground shadow">
                  No suggestions yet - try refreshing once your location is locked.
                </div>
              )}
            </div>
          </aside>
        </main>
      </div>
    </ThemeProvider>
  );
}

function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
) {
  return calculateDistanceKm(lat1, lon1, lat2, lon2);
}

function formatPlacesQuotaError(resetAt: string | null): string {
  if (!resetAt) {
    return "Today's nearby discovery limit has been reached. Please try again tomorrow.";
  }
  const resetDate = new Date(resetAt);
  if (!Number.isFinite(resetDate.getTime())) {
    return "Today's nearby discovery limit has been reached. Please try again tomorrow.";
  }
  const formattedReset = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(resetDate);
  return `Today's nearby discovery limit has been reached. It resets ${formattedReset}.`;
}

export default App;
