import { useMemo, useState, useEffect } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { SuggestionCard } from "./components/SuggestionCard";
import { MapView } from "./components/MapView";
import { ChatRecommendation } from "./api/chat";
import { ThemeProvider } from "./context/ThemeContext";
import { ThemeToggle } from "./components/ThemeToggle";

const sampleSuggestions = [
  {
    title: "Mock Ramen House",
    description:
      "Rich tonkotsu broth, chili oil drizzle, and cozy counter seating. A go-to when you want comfort heat.",
    tags: ["Ramen", "Cozy", "Spicy"],
    distance: "0.8 km",
    rating: 4.8,
  },
  {
    title: "Pho Aurora",
    description:
      "Northern-style pho with fresh herbs and veggie-friendly broth options for lighter cravings.",
    tags: ["Pho", "Light", "Herbal"],
    distance: "1.2 km",
    rating: 4.6,
  },
  {
    title: "Chili Garden Tapas",
    description:
      "Shared small plates with Szechuan flair. Perfect for friends who want buzz plus heat.",
    tags: ["Szechuan", "Group Friendly"],
    distance: "1.5 km",
    rating: 4.7,
  },
];

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
                These recommendations are static for now. They will connect to the
                backend once live APIs are in place.
              </p>
            </div>
            <div className="grid gap-4">
              {sampleSuggestions.map((suggestion) => (
                <SuggestionCard key={suggestion.title} {...suggestion} />
              ))}
            </div>
          </aside>
        </main>
      </div>
    </ThemeProvider>
  );
}

export default App;
