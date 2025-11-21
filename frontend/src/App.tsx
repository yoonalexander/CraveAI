import { useMemo, useState, useEffect } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { SuggestionCard } from "./components/SuggestionCard";
import { MapView } from "./components/MapView";
import { ChatRecommendation } from "./api/chat";
import { ThemeProvider } from "./context/ThemeContext";
import { ThemeToggle } from "./components/ThemeToggle";
import { fetchSuggestions, Suggestion } from "./api/places";

const SUGGESTION_TIMEOUT_MS = 30000;

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
  const [mapRecommendations, setMapRecommendations] = useState<
    ChatRecommendation[]
  >([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionIndex, setSuggestionIndex] = useState(0);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setLocationStatus(
        "Geolocation not supported; using Hamilton, ON as a fallback.",
      );
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setLocationStatus("Live location locked. Refining searches nearby.");
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
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      },
    );
  }, []);

  useEffect(() => {
    const fetchNearby = async () => {
      let timeoutId: number | undefined;
      let timedOut = false;

      setIsLoadingSuggestions(true);
      setSuggestionError(null);

      timeoutId = window.setTimeout(() => {
        timedOut = true;
        setSuggestionError(
          "We couldn't load suggestions in time. Check location permissions and your Google Places API key.",
        );
        setIsLoadingSuggestions(false);
      }, SUGGESTION_TIMEOUT_MS);

      try {
        const loc = userLocation || HAMILTON_FALLBACK;
        const data = await fetchSuggestions(loc.lat, loc.lng);
        if (!timedOut) {
          setSuggestions(data);
          if (data.length === 0) {
            setSuggestionError(
              "No nearby restaurants found. Try widening your location radius.",
            );
          }
        }
      } catch (error) {
        console.error("Failed to fetch suggestions:", error);
        if (!timedOut) {
          setSuggestionError(
            "Failed to load suggestions. Verify location access and your Google Places API setup.",
          );
        }
      } finally {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        if (!timedOut) {
          setIsLoadingSuggestions(false);
        }
      }
    };

    fetchNearby();
  }, [userLocation]);

  useEffect(() => {
    if (suggestions.length === 0) return;
    const interval = setInterval(() => {
      setSuggestionIndex((prev) => (prev + 1) % suggestions.length);
    }, 30000);
    return () => clearInterval(interval);
  }, [suggestions]);

  const visibleSuggestions = useMemo(() => {
    if (suggestions.length === 0) return [];
    const result = [];
    for (let i = 0; i < Math.min(3, suggestions.length); i++) {
      result.push(suggestions[(suggestionIndex + i) % suggestions.length]);
    }
    return result;
  }, [suggestions, suggestionIndex]);

  const chatLocation = useMemo(() => {
    if (userLocation) {
      return {
        ...userLocation,
        radius: 5000,
      };
    }
    return HAMILTON_FALLBACK;
  }, [userLocation]);

  const mapLocation = userLocation ?? {
    lat: HAMILTON_FALLBACK.lat,
    lng: HAMILTON_FALLBACK.lng,
  };

  return (
    <ThemeProvider defaultTheme="light" storageKey="craveai-theme">
      <div className="min-h-screen bg-background text-foreground transition-colors duration-300">
        <header className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 pb-10 pt-14 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.32em] text-primary font-bold">
              craveai
            </p>
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
            <div className="rounded-3xl border border-border bg-secondary/50 px-5 py-4 text-sm text-muted-foreground shadow-lg backdrop-blur-sm">
              <p className="font-semibold text-foreground">Build Status</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
                <li>Chat UI scaffolded with placeholder flow.</li>
                <li>Favorites & map views queued for upcoming sprints.</li>
                <li>Backend RAG pipeline mocked until API keys are ready.</li>
              </ul>
            </div>
          </div>
        </header>

        <main className="mx-auto grid w-full max-w-6xl gap-6 px-6 pb-16 md:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <section className="h-[600px] md:h-[720px]">
            <ChatPanel
              location={chatLocation}
              locationStatus={locationStatus}
              onRecommendations={setMapRecommendations}
            />
          </section>
          <aside className="flex flex-col gap-4">
            <MapView
              userLocation={mapLocation}
              recommendations={mapRecommendations}
              hasLiveLocation={Boolean(userLocation)}
              statusMessage={locationStatus}
            />
            <div className="rounded-3xl border border-border bg-secondary/40 p-5 text-foreground">
              <h2 className="text-lg font-semibold">
                Today&apos;s Suggested Spots
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Top rated spots near you. Cycling every 30 seconds.
              </p>
              {isLoadingSuggestions && !suggestionError && (
                <div className="mt-4 flex items-center gap-4 rounded-2xl bg-secondary/70 p-3 shadow-inner">
                  <div className="relative h-10 w-10">
                    <div className="absolute inset-0 rounded-full border-2 border-primary/25" />
                    <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  </div>
                  <div className="text-sm">
                    <p className="font-medium text-foreground">
                      Finding nearby restaurants...
                    </p>
                    <p className="text-muted-foreground">
                      Using your location and Google Places.
                    </p>
                  </div>
                </div>
              )}
              {suggestionError && (
                <div className="mt-4 rounded-2xl border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                  {suggestionError}
                </div>
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
  const R = 6371; // Radius of the earth in km
  const dLat = deg2rad(lat2 - lat1);
  const dLon = deg2rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(deg2rad(lat1)) *
    Math.cos(deg2rad(lat2)) *
    Math.sin(dLon / 2) *
    Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const d = R * c; // Distance in km
  return d;
}

function deg2rad(deg: number) {
  return deg * (Math.PI / 180);
}

export default App;
