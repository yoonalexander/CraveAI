import { useCallback, useEffect, useMemo, useState } from "react";

import type { ChatRecommendation } from "./api/chat";
import { fetchSuggestions, PlacesQuotaError, Suggestion } from "./api/places";
import { fetchCurrentWeather, CurrentWeather } from "./api/weather";
import { AccountMenu } from "./components/AccountMenu";
import { ChatPanel } from "./components/ChatPanel";
import { DiscoveryPage } from "./components/DiscoveryPage";
import { MenuIcon, PinIcon } from "./components/Icons";
import { LocationDialog, SelectedLocation } from "./components/LocationDialog";
import { MapView } from "./components/MapView";
import { MobileChatSheet } from "./components/MobileChatSheet";
import { SearchToolbar } from "./components/SearchToolbar";
import { Sidebar } from "./components/Sidebar";
import { GoogleMapsProvider, useGoogleMaps } from "./context/GoogleMapsContext";
import type { Coordinates, SearchArea } from "./types/searchArea";
import { filterSuggestions, SuggestionFilter } from "./utils/suggestionPool";

const SUGGESTION_TIMEOUT_MS = 90_000;
const SEARCH_RADIUS_METERS = 5_000;
const SIDEBAR_STORAGE_KEY = "craveai-sidebar-collapsed";

const HAMILTON_FALLBACK = {
  lat: 43.2557,
  lng: -79.8711,
  city: "Hamilton, ON",
};

type LocationSource = "device" | "manual" | "fallback";

const placeholderPages: Record<string, { eyebrow: string; title: string; copy: string }> = {
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
  const [mobileChatExpanded, setMobileChatExpanded] = useState(false);
  const [locationDialogOpen, setLocationDialogOpen] = useState(false);

  const [originLocation, setOriginLocation] = useState<Coordinates | null>(null);
  const [locationSource, setLocationSource] = useState<LocationSource>("fallback");
  const [locationStatus, setLocationStatus] = useState("Finding your location…");
  const [locationReady, setLocationReady] = useState(false);
  const [searchArea, setSearchArea] = useState<SearchArea | null>(null);
  const [requestedArea, setRequestedArea] = useState<SearchArea | null>(null);
  const [lastFailedArea, setLastFailedArea] = useState<SearchArea | null>(null);
  const [recenterVersion, setRecenterVersion] = useState(0);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [isResolvingArea, setIsResolvingArea] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionQuotaResetAt, setSuggestionQuotaResetAt] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<SuggestionFilter>>(new Set());
  const [mapRecommendations, setMapRecommendations] = useState<ChatRecommendation[]>([]);
  const [weather, setWeather] = useState<CurrentWeather | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);

  useEffect(() => {
    const handlePopState = () => setCurrentPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const confirmLocation = useCallback((
    coordinates: Coordinates,
    label: string,
    source: LocationSource,
    status: string,
  ) => {
    const area: SearchArea = {
      center: coordinates,
      radius: SEARCH_RADIUS_METERS,
      label,
    };
    setOriginLocation(coordinates);
    setLocationSource(source);
    setLocationStatus(status);
    setLocationReady(true);
    setSearchArea(area);
    setRequestedArea(area);
    setLastFailedArea(null);
    setRecenterVersion((version) => version + 1);
    setMapRecommendations([]);
  }, []);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      confirmLocation(
        { lat: HAMILTON_FALLBACK.lat, lng: HAMILTON_FALLBACK.lng },
        HAMILTON_FALLBACK.city,
        "fallback",
        "Geolocation is unavailable; using Hamilton, ON.",
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        confirmLocation(
          { lat: position.coords.latitude, lng: position.coords.longitude },
          "Current location",
          "device",
          "Live location locked.",
        );
      },
      (error) => {
        confirmLocation(
          { lat: HAMILTON_FALLBACK.lat, lng: HAMILTON_FALLBACK.lng },
          HAMILTON_FALLBACK.city,
          "fallback",
          error.code === error.PERMISSION_DENIED
            ? "Location permission denied; using Hamilton, ON."
            : "Unable to read your location; using Hamilton, ON.",
        );
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 },
    );
  }, [confirmLocation]);

  useEffect(() => {
    if (!mapsLoaded || !searchArea || searchArea.bounds || searchArea.label !== "Current location") return;
    let active = true;
    reverseGeocode(searchArea.center).then((label) => {
      if (!active || !label) return;
      setSearchArea((area) => area && sameCoordinates(area.center, searchArea.center) ? { ...area, label } : area);
      setRequestedArea((area) => area && sameCoordinates(area.center, searchArea.center) ? { ...area, label } : area);
    });
    return () => { active = false; };
  }, [mapsLoaded, searchArea]);

  useEffect(() => {
    if (!requestedArea) return;
    const controller = new AbortController();
    let active = true;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, SUGGESTION_TIMEOUT_MS);

    setIsLoadingSuggestions(true);
    setSuggestionError(null);
    setSuggestionQuotaResetAt(null);
    fetchSuggestions(
      requestedArea.center.lat,
      requestedArea.center.lng,
      requestedArea.radius,
      controller.signal,
      requestedArea.bounds,
    )
      .then((places) => {
        if (!active) return;
        setSuggestions(places);
        setSearchArea(requestedArea);
        setLastFailedArea(null);
        setMapRecommendations([]);
        if (!places.length) setSuggestionError("No restaurants were found in this map area.");
      })
      .catch((reason) => {
        if (!active) return;
        if (controller.signal.aborted && timedOut) {
          setLastFailedArea(requestedArea);
          setSuggestionError("We couldn't load this area in time. Your previous results are still shown.");
        } else if (reason instanceof PlacesQuotaError) {
          setLastFailedArea(requestedArea);
          setSuggestionQuotaResetAt(reason.resetAt);
          setSuggestionError(formatPlacesQuotaError(reason.resetAt));
        } else if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setLastFailedArea(requestedArea);
          setSuggestionError("We couldn't search this area. Your previous results are still shown.");
        }
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) {
          setIsLoadingSuggestions(false);
          setRequestedArea(null);
        }
      });

    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [requestedArea]);

  useEffect(() => {
    if (!searchArea) return;
    const controller = new AbortController();
    setWeatherLoading(true);
    fetchCurrentWeather(searchArea.center.lat, searchArea.center.lng, controller.signal)
      .then(setWeather)
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setWeather(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setWeatherLoading(false);
      });
    return () => controller.abort();
  }, [searchArea]);

  const filteredSuggestions = useMemo(
    () => filterSuggestions(suggestions, activeFilters),
    [activeFilters, suggestions],
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
      setMobileChatExpanded(false);
    }
  }, []);

  const selectLocation = (selection: SelectedLocation) => {
    confirmLocation(
      { lat: selection.lat, lng: selection.lng },
      selection.label,
      selection.source,
      selection.source === "device" ? "Live location locked." : "Using your selected location.",
    );
    setLocationDialogOpen(false);
  };

  const searchViewport = async (area: SearchArea) => {
    if (isLoadingSuggestions || isResolvingArea) return;
    setIsResolvingArea(true);
    try {
      const label = mapsLoaded ? await reverseGeocode(area.center) : null;
      setRequestedArea({ ...area, label: label || "Selected map area" });
    } finally {
      setIsResolvingArea(false);
    }
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((collapsed) => {
      const next = !collapsed;
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      return next;
    });
  };

  const toggleFilter = (filter: SuggestionFilter) => {
    setActiveFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  };

  const retrySearch = () => {
    const area = lastFailedArea || searchArea;
    if (area && !isLoadingSuggestions) setRequestedArea({ ...area });
  };

  const homeVisible = currentPath === "/";
  const discoveryVisible = currentPath === "/discovery";
  const searchRouteVisible = homeVisible || discoveryVisible;
  const placeholder = placeholderPages[currentPath];
  const chatLocation = searchArea
    ? {
        ...searchArea.center,
        city: searchArea.label,
        radius: searchArea.radius,
        bounds: searchArea.bounds,
      }
    : null;

  const toolbar = (
    <SearchToolbar
      activeFilters={activeFilters}
      area={searchArea}
      canRetry={!suggestionQuotaResetAt}
      count={filteredSuggestions.length}
      error={suggestionError}
      isLoading={isLoadingSuggestions || isResolvingArea}
      onChangeLocation={() => setLocationDialogOpen(true)}
      onClearFilters={() => setActiveFilters(new Set())}
      onRetry={retrySearch}
      onToggleFilter={toggleFilter}
    />
  );

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
          {searchRouteVisible ? (
            <button
              className="mobile-location-pill"
              onClick={() => setLocationDialogOpen(true)}
              type="button"
            >
              <PinIcon />
              <span>
                <strong>{searchArea?.label || "Finding your location…"}</strong>
                <small>
                  {isLoadingSuggestions || isResolvingArea
                    ? "Updating map area…"
                    : suggestionError
                      ? "Search needs attention"
                      : `${filteredSuggestions.length} restaurant${filteredSuggestions.length === 1 ? "" : "s"} in map area`}
                </small>
              </span>
            </button>
          ) : null}
          <AccountMenu />
        </header>

        <main className="crave-content">
          {homeVisible ? (
            <div className="search-view home-view">
              {toolbar}
              <div className="home-split">
                <section className="home-chat" aria-label="Chat">
                  <MobileChatSheet expanded={mobileChatExpanded} onExpandedChange={setMobileChatExpanded}>
                    <ChatPanel
                      candidatePlaces={filteredSuggestions}
                      key={chatSession}
                      location={chatLocation}
                      onConversationStart={() => setMobileChatExpanded(true)}
                      onRecommendations={setMapRecommendations}
                    />
                  </MobileChatSheet>
                </section>
                <section className="home-map">
                  <MapView
                    confirmedArea={searchArea}
                    isLocating={!locationReady}
                    isSearching={isLoadingSuggestions || isResolvingArea}
                    locationLabel={searchArea?.label || locationStatus}
                    onSearchArea={(area) => { void searchViewport(area); }}
                    originIsDevice={locationSource === "device"}
                    originLocation={originLocation}
                    recenterVersion={recenterVersion}
                    recommendations={mapRecommendations}
                    suggestions={filteredSuggestions}
                  />
                </section>
              </div>
            </div>
          ) : discoveryVisible ? (
            <div className="search-view discovery-view">
              {toolbar}
              <DiscoveryPage
                canRetry={!suggestionQuotaResetAt}
                error={suggestionError}
                isLoading={isLoadingSuggestions}
                onRetry={retrySearch}
                origin={originLocation}
                suggestions={filteredSuggestions}
              />
            </div>
          ) : (
            <PlaceholderPage content={placeholder} onBack={() => navigate("/", true)} />
          )}
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

async function reverseGeocode(coordinates: Coordinates): Promise<string | null> {
  if (typeof google === "undefined" || !google.maps?.Geocoder) return null;
  try {
    const response = await new google.maps.Geocoder().geocode({ location: coordinates });
    const result = response.results?.[0];
    if (!result) return null;
    const city = findAddressComponent(result.address_components, "locality") ||
      findAddressComponent(result.address_components, "postal_town") ||
      findAddressComponent(result.address_components, "administrative_area_level_2");
    const province = findAddressComponent(result.address_components, "administrative_area_level_1", true);
    return city ? (province && city !== province ? `${city}, ${province}` : city) : result.formatted_address;
  } catch {
    return null;
  }
}

function sameCoordinates(first: Coordinates, second: Coordinates): boolean {
  return first.lat === second.lat && first.lng === second.lng;
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
