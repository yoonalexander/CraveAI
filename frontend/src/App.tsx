import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { ChatRecommendation } from "./api/chat";
import {
  fetchSuggestions,
  PlacesQuotaError,
  Suggestion,
} from "./api/places";
import { fetchCurrentWeather, CurrentWeather } from "./api/weather";
import { AccountMenu } from "./components/AccountMenu";
import { ChatPanel } from "./components/ChatPanel";
import { ChevronDownIcon, MenuIcon } from "./components/Icons";
import {
  LocationDialog,
  SelectedLocation,
} from "./components/LocationDialog";
import { MapView, PlaceFilter } from "./components/MapView";
import { Sidebar } from "./components/Sidebar";
import { SuggestionsPanel } from "./components/SuggestionsPanel";
import { GoogleMapsProvider, useGoogleMaps } from "./context/GoogleMapsContext";
import {
  calculateDistanceKm,
  filterSuggestions,
  getNextSuggestionIndex,
  getVisibleSuggestions,
  MATERIAL_LOCATION_CHANGE_KM,
} from "./utils/suggestionPool";

const SUGGESTION_ROTATION_MS = 30000;
const SUGGESTION_TIMEOUT_MS = 90000;
const SEARCH_RADIUS_METERS = 5000;
const SIDEBAR_STORAGE_KEY = "craveai-sidebar-collapsed";

const HAMILTON_FALLBACK = {
  lat: 43.2557,
  lng: -79.8711,
  city: "Hamilton, ON",
  radius: SEARCH_RADIUS_METERS,
};

type Coordinates = { lat: number; lng: number };
type LocationSource = "device" | "manual" | "fallback";

const placeholderPages: Record<string, { eyebrow: string; title: string; copy: string }> = {
  "/discovery": {
    eyebrow: "Discovery",
    title: "A better way to browse is coming.",
    copy: "Soon you’ll be able to explore neighbourhood guides, cuisines, and curated collections here.",
  },
  "/likes": {
    eyebrow: "Likes",
    title: "Your favourite spots will live here.",
    copy: "We’re designing a simple place to revisit and organize restaurants you’ve saved.",
  },
  "/history": {
    eyebrow: "History",
    title: "Conversation history is coming soon.",
    copy: "Chats are not stored today. When history arrives, it will be introduced with clear privacy controls.",
  },
  "/pricing": {
    eyebrow: "Plans and pricing",
    title: "More ways to use CraveAI are on the menu.",
    copy: "Plan details and higher recommendation limits will appear here when they’re ready.",
  },
  "/settings": {
    eyebrow: "Settings",
    title: "Personal controls are being prepared.",
    copy: "Preference, accessibility, and notification settings will be available in a future update.",
  },
  "/help": {
    eyebrow: "Help",
    title: "A CraveAI help centre is coming.",
    copy: "For now, return to New chat and describe the food, mood, budget, or area you have in mind.",
  },
};

export default function App(): JSX.Element {
  return (
    <GoogleMapsProvider>
      <CraveApplication />
    </GoogleMapsProvider>
  );
}

function CraveApplication(): JSX.Element {
  const { isLoaded: mapsLoaded } = useGoogleMaps();
  const [currentPath, setCurrentPath] = useState(() => normalizePath(window.location.pathname));
  const [chatSession, setChatSession] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarPreference);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [locationDialogOpen, setLocationDialogOpen] = useState(false);
  const [mapMobileOpen, setMapMobileOpen] = useState(false);
  const [spotsMobileOpen, setSpotsMobileOpen] = useState(true);

  const [userLocation, setUserLocation] = useState<Coordinates | null>(null);
  const [locationSource, setLocationSource] = useState<LocationSource>("fallback");
  const [locationLabel, setLocationLabel] = useState("Finding your location…");
  const [locationStatus, setLocationStatus] = useState("Calibrating your location…");
  const [locationReady, setLocationReady] = useState(false);
  const [locationRefreshVersion, setLocationRefreshVersion] = useState(0);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionQuotaResetAt, setSuggestionQuotaResetAt] = useState<string | null>(null);
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [rotationVersion, setRotationVersion] = useState(0);
  const [activeFilters, setActiveFilters] = useState<Set<PlaceFilter>>(new Set());
  const [mapRecommendations, setMapRecommendations] = useState<ChatRecommendation[]>([]);
  const [weather, setWeather] = useState<CurrentWeather | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);

  const lastSuggestionLocation = useRef<Coordinates | null>(null);
  const lastRefreshVersion = useRef(-1);

  useEffect(() => {
    const handlePopState = () => setCurrentPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      useFallbackLocation("Geolocation is not supported; using Hamilton, ON.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({ lat: position.coords.latitude, lng: position.coords.longitude });
        setLocationSource("device");
        setLocationLabel("Current location");
        setLocationStatus("Live location locked. Refining searches nearby.");
        setLocationReady(true);
      },
      (error) => {
        useFallbackLocation(
          error.code === error.PERMISSION_DENIED
            ? "Location permission denied; using Hamilton, ON."
            : "Unable to read your location; using Hamilton, ON.",
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }, []);

  const useFallbackLocation = (status: string) => {
    setUserLocation({ lat: HAMILTON_FALLBACK.lat, lng: HAMILTON_FALLBACK.lng });
    setLocationSource("fallback");
    setLocationLabel(HAMILTON_FALLBACK.city);
    setLocationStatus(status);
    setLocationReady(true);
  };

  useEffect(() => {
    if (!mapsLoaded || !userLocation) return;
    let active = true;
    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ location: userLocation }, (results, status) => {
      if (!active || status !== "OK" || !results?.length) return;
      const components = results[0].address_components;
      const city = findAddressComponent(components, "locality") ||
        findAddressComponent(components, "postal_town") ||
        findAddressComponent(components, "administrative_area_level_2");
      const province = findAddressComponent(components, "administrative_area_level_1", true);
      if (city) setLocationLabel(province && city !== province ? `${city}, ${province}` : city);
    });
    return () => {
      active = false;
    };
  }, [mapsLoaded, userLocation]);

  useEffect(() => {
    if (!locationReady || !userLocation) return;
    const isManualRefresh = locationRefreshVersion !== lastRefreshVersion.current;
    const previous = lastSuggestionLocation.current;
    if (
      !isManualRefresh &&
      previous &&
      calculateDistanceKm(previous.lat, previous.lng, userLocation.lat, userLocation.lng) <
        MATERIAL_LOCATION_CHANGE_KM
    ) {
      return;
    }

    const controller = new AbortController();
    let active = true;
    let timedOut = false;
    const fetchNearby = async () => {
      setIsLoadingSuggestions(true);
      setSuggestionError(null);
      setSuggestionQuotaResetAt(null);
      setSuggestions([]);
      setSuggestionIndex(0);
      const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, SUGGESTION_TIMEOUT_MS);
      try {
        const data = await fetchSuggestions(
          userLocation.lat,
          userLocation.lng,
          SEARCH_RADIUS_METERS,
          controller.signal,
        );
        setSuggestions(data);
        lastSuggestionLocation.current = userLocation;
        lastRefreshVersion.current = locationRefreshVersion;
        if (!data.length) setSuggestionError("No nearby restaurants were found.");
      } catch (reason) {
        if (!active) return;
        if (controller.signal.aborted && timedOut) {
          setSuggestionError("We couldn't load suggestions in time.");
        } else if (reason instanceof PlacesQuotaError) {
          setSuggestionQuotaResetAt(reason.resetAt);
          setSuggestionError(formatPlacesQuotaError(reason.resetAt));
        } else {
          setSuggestionError("We couldn't load nearby spots. Please try again.");
        }
      } finally {
        window.clearTimeout(timeout);
        if (active) setIsLoadingSuggestions(false);
      }
    };
    void fetchNearby();
    return () => {
      active = false;
      controller.abort();
    };
  }, [locationReady, locationRefreshVersion, userLocation]);

  useEffect(() => {
    if (!userLocation) return;
    const controller = new AbortController();
    setWeatherLoading(true);
    setWeather(null);
    fetchCurrentWeather(userLocation.lat, userLocation.lng, controller.signal)
      .then(setWeather)
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setWeather(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setWeatherLoading(false);
      });
    return () => controller.abort();
  }, [userLocation]);

  const filteredSuggestions = useMemo(() => {
    return filterSuggestions(suggestions, activeFilters);
  }, [activeFilters, suggestions]);

  useEffect(() => {
    setSuggestionIndex(0);
    setRotationVersion((value) => value + 1);
  }, [activeFilters]);

  const advanceSuggestions = useCallback(() => {
    setSuggestionIndex((current) => getNextSuggestionIndex(current, filteredSuggestions.length));
  }, [filteredSuggestions.length]);

  useEffect(() => {
    if (filteredSuggestions.length <= 3) return;
    const interval = window.setInterval(advanceSuggestions, SUGGESTION_ROTATION_MS);
    return () => window.clearInterval(interval);
  }, [advanceSuggestions, filteredSuggestions.length, rotationVersion]);

  const visibleSuggestions = useMemo(
    () => getVisibleSuggestions(filteredSuggestions, suggestionIndex),
    [filteredSuggestions, suggestionIndex],
  );

  const navigate = useCallback((path: string, resetChat = false) => {
    const normalized = normalizePath(path);
    if (normalized !== normalizePath(window.location.pathname)) {
      window.history.pushState({}, "", normalized);
    }
    setCurrentPath(normalized);
    setMobileMenuOpen(false);
    if (resetChat) {
      setChatSession((session) => session + 1);
      setMapRecommendations([]);
    }
  }, []);

  const selectLocation = (selection: SelectedLocation) => {
    setUserLocation({ lat: selection.lat, lng: selection.lng });
    setLocationSource(selection.source);
    setLocationLabel(selection.label);
    setLocationStatus(
      selection.source === "device"
        ? "Live location locked. Refining searches nearby."
        : "Using your selected location for nearby searches.",
    );
    setLocationReady(true);
    setLocationRefreshVersion((version) => version + 1);
    setLocationDialogOpen(false);
    setMapRecommendations([]);
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((collapsed) => {
      const next = !collapsed;
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      return next;
    });
  };

  const toggleFilter = (filter: PlaceFilter) => {
    setActiveFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  };

  const homeVisible = currentPath === "/";
  const placeholder = placeholderPages[currentPath];
  const chatLocation = userLocation
    ? { ...userLocation, city: locationLabel, radius: SEARCH_RADIUS_METERS }
    : null;

  return (
    <div className={`crave-app${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        collapsed={sidebarCollapsed}
        currentPath={currentPath}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
        onNavigate={navigate}
        onToggle={toggleSidebar}
        weather={weather}
        weatherLoading={weatherLoading}
      />

      <div className="crave-main">
        <header className="crave-topbar">
          <button
            aria-label="Open navigation"
            className="mobile-menu-button"
            onClick={() => setMobileMenuOpen(true)}
            type="button"
          >
            <MenuIcon />
          </button>
          <a className="crave-wordmark" href="/" onClick={(event) => {
            event.preventDefault();
            navigate("/");
          }}>
            CRAVEAI
          </a>
          <AccountMenu />
        </header>

        <main className="crave-content">
          <div className={`crave-workspace${homeVisible ? "" : " is-route-hidden"}`}>
            <section className="workspace-chat">
              <ChatPanel
                candidatePlaces={filteredSuggestions}
                key={chatSession}
                location={chatLocation}
                onRecommendations={setMapRecommendations}
              />
            </section>

            <section className={`workspace-map mobile-collapsible${mapMobileOpen ? " is-open" : ""}`}>
              <button
                aria-expanded={mapMobileOpen}
                className="mobile-section-toggle"
                onClick={() => setMapMobileOpen((open) => !open)}
                type="button"
              >
                Live map <ChevronDownIcon />
              </button>
              <div className="mobile-section-content">
                <MapView
                  activeFilters={activeFilters}
                  hasLiveLocation={locationSource === "device"}
                  isLocating={!locationReady}
                  locationLabel={locationLabel}
                  onChangeLocation={() => setLocationDialogOpen(true)}
                  onClearFilters={() => setActiveFilters(new Set())}
                  onToggleFilter={toggleFilter}
                  radiusKm={SEARCH_RADIUS_METERS / 1000}
                  recommendations={mapRecommendations}
                  statusMessage={locationStatus}
                  suggestions={filteredSuggestions}
                  userLocation={userLocation}
                />
              </div>
            </section>

            <aside className={`workspace-spots mobile-collapsible${spotsMobileOpen ? " is-open" : ""}`}>
              <button
                aria-expanded={spotsMobileOpen}
                className="mobile-section-toggle"
                onClick={() => setSpotsMobileOpen((open) => !open)}
                type="button"
              >
                Suggested spots <ChevronDownIcon />
              </button>
              <div className="mobile-section-content">
                <SuggestionsPanel
                  canRetry={!suggestionQuotaResetAt}
                  error={suggestionError}
                  isLoading={isLoadingSuggestions}
                  onRetry={() => setLocationRefreshVersion((version) => version + 1)}
                  onViewMore={() => {
                    advanceSuggestions();
                    setRotationVersion((version) => version + 1);
                  }}
                  suggestions={visibleSuggestions}
                  totalCount={filteredSuggestions.length}
                  userLocation={userLocation}
                />
              </div>
            </aside>
          </div>

          {!homeVisible ? (
            <PlaceholderPage
              content={placeholder}
              onBack={() => navigate("/")}
            />
          ) : null}
        </main>
      </div>

      <LocationDialog
        onClose={() => setLocationDialogOpen(false)}
        onSelect={selectLocation}
        open={locationDialogOpen}
      />
    </div>
  );
}

function PlaceholderPage({
  content,
  onBack,
}: {
  content: { eyebrow: string; title: string; copy: string } | undefined;
  onBack: () => void;
}): JSX.Element {
  return (
    <section className="placeholder-page">
      <img alt="" src="/craveai-pin.svg" />
      <p>{content?.eyebrow || "Not found"}</p>
      <h1>{content?.title || "That page isn’t on the menu."}</h1>
      <span>{content?.copy || "Return to CraveAI and start a new restaurant search."}</span>
      <button onClick={onBack} type="button">Start a new chat</button>
    </section>
  );
}

function normalizePath(path: string): string {
  const normalized = path.replace(/\/+$/, "");
  return normalized || "/";
}

function readSidebarPreference(): boolean {
  try {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (stored !== null) return stored === "true";
    return window.matchMedia("(max-width: 1120px)").matches;
  } catch {
    return false;
  }
}

function findAddressComponent(
  components: google.maps.GeocoderAddressComponent[],
  type: string,
  short = false,
): string | null {
  const component = components.find((item) => item.types.includes(type));
  if (!component) return null;
  return short ? component.short_name : component.long_name;
}

function formatPlacesQuotaError(resetAt: string | null): string {
  if (!resetAt) return "Today's nearby discovery limit has been reached. Please try again tomorrow.";
  const resetDate = new Date(resetAt);
  if (!Number.isFinite(resetDate.getTime())) {
    return "Today's nearby discovery limit has been reached. Please try again tomorrow.";
  }
  return `Today's nearby discovery limit has been reached. It resets ${new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(resetDate)}.`;
}
