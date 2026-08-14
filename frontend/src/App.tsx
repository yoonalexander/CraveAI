import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatRecommendation } from "./api/chat";
import { fetchSuggestions, PlacesQuotaError, Suggestion, verifyDietaryEvidence } from "./api/places";
import { listSavedPlaces } from "./api/favorites";
import { fetchCurrentWeather, CurrentWeather } from "./api/weather";
import { fetchPreferences, Preferences } from "./api/product";
import { AccountMenu } from "./components/AccountMenu";
import { ChatPanel } from "./components/ChatPanel";
import { DiscoveryPage } from "./components/DiscoveryPage";
import { MenuIcon, PinIcon } from "./components/Icons";
import { LocationDialog, SelectedLocation } from "./components/LocationDialog";
import { MapView } from "./components/MapView";
import { MobileChatSheet } from "./components/MobileChatSheet";
import { SearchToolbar } from "./components/SearchToolbar";
import { Sidebar } from "./components/Sidebar";
import {
  HelpPage,
  HistoryPage,
  LegalPage,
  LikesPage,
  PolicyGate,
  PricingPage,
  SettingsPage,
} from "./components/ProductPages";
import { GoogleMapsProvider, useGoogleMaps } from "./context/GoogleMapsContext";
import { useAuth } from "./context/AuthContext";
import type { Coordinates, SearchArea } from "./types/searchArea";
import {
  filterSuggestions,
  DEFAULT_ADVANCED_FILTERS,
  AdvancedFilters,
  mergeSuggestionsForBounds,
  SuggestionFilter,
} from "./utils/suggestionPool";

const SUGGESTION_TIMEOUT_MS = 90_000;
const SEARCH_RADIUS_METERS = 5_000;
const SIDEBAR_STORAGE_KEY = "craveai-sidebar-collapsed";

const TORONTO_FALLBACK = {
  lat: 43.6532,
  lng: -79.3832,
  city: "Toronto, ON",
};

type LocationSource = "device" | "manual" | "fallback";

export default function App(): JSX.Element {
  return (
    <GoogleMapsProvider>
      <CraveApplication />
    </GoogleMapsProvider>
  );
}

function CraveApplication(): JSX.Element {
  const { isLoaded: mapsLoaded } = useGoogleMaps();
  const { user, loading: authLoading } = useAuth();
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
  const suggestionsRef = useRef<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [isResolvingArea, setIsResolvingArea] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionQuotaResetAt, setSuggestionQuotaResetAt] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<SuggestionFilter>>(new Set());
  const [advancedFilters, setAdvancedFilters] = useState<AdvancedFilters>(DEFAULT_ADVANCED_FILTERS);
  const [mapRecommendations, setMapRecommendations] = useState<ChatRecommendation[]>([]);
  const [weather, setWeather] = useState<CurrentWeather | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [savedPlaceIds, setSavedPlaceIds] = useState<Set<string>>(new Set());
  const [dietaryEvidence, setDietaryEvidence] = useState<{
    key: string; loading: boolean; error: string | null; matches: Map<string, string[]>;
  }>({ key: "", loading: false, error: null, matches: new Map() });
  const [dietaryRetry, setDietaryRetry] = useState(0);
  const locationInitialized = useRef(false);

  useEffect(() => {
    setPreferencesLoaded(false);
    if (!user) { setPreferences(null); setSavedPlaceIds(new Set()); setPreferencesLoaded(true); return; }
    let active = true;
    void Promise.all([fetchPreferences(), listSavedPlaces()])
      .then(([value, saved]) => {
        if (!active) return;
        setPreferences(value);
        setSavedPlaceIds(new Set(saved.flatMap((item) => item.place_id ? [item.place_id] : [])));
      })
      .catch(() => undefined)
      .finally(() => { if (active) setPreferencesLoaded(true); });
    return () => { active = false; };
  }, [user]);

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
    radius = SEARCH_RADIUS_METERS,
  ) => {
    const area: SearchArea = {
      center: coordinates,
      radius,
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
    if (authLoading || !preferencesLoaded || locationInitialized.current) return;
    locationInitialized.current = true;
    if (preferences?.default_location) {
      confirmLocation(
        { lat: preferences.default_location.lat, lng: preferences.default_location.lng },
        preferences.default_location.label,
        "manual",
        "Using your saved default location.",
        preferences.default_radius_meters,
      );
      return;
    }
    if (!("geolocation" in navigator)) {
      confirmLocation(
        { lat: TORONTO_FALLBACK.lat, lng: TORONTO_FALLBACK.lng },
        TORONTO_FALLBACK.city,
        "fallback",
        "Geolocation is unavailable; using Toronto, ON.",
        preferences?.default_radius_meters,
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
          preferences?.default_radius_meters,
        );
      },
      (error) => {
        confirmLocation(
          { lat: TORONTO_FALLBACK.lat, lng: TORONTO_FALLBACK.lng },
          TORONTO_FALLBACK.city,
          "fallback",
          error.code === error.PERMISSION_DENIED
            ? "Location permission denied; using Toronto, ON."
            : "Unable to read your location; using Toronto, ON.",
          preferences?.default_radius_meters,
        );
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 },
    );
  }, [authLoading, confirmLocation, preferences, preferencesLoaded]);

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
        const mergedPlaces = mergeSuggestionsForBounds(
          suggestionsRef.current,
          places,
          requestedArea.bounds,
        );
        suggestionsRef.current = mergedPlaces;
        setSuggestions(mergedPlaces);
        setSearchArea(requestedArea);
        setLastFailedArea(null);
        setMapRecommendations([]);
        if (!mergedPlaces.length) setSuggestionError("No restaurants were found in this map area.");
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

  const dietaryEvidenceKey = `${advancedFilters.dietary.slice().sort().join("|")}::${suggestions.map((item) => item.place_id).sort().join("|")}`;
  useEffect(() => {
    if (!advancedFilters.dietary.length || !suggestions.length) {
      setDietaryEvidence({ key: dietaryEvidenceKey, loading: false, error: null, matches: new Map() });
      return;
    }
    const controller = new AbortController();
    setDietaryEvidence((current) => ({ ...current, key: dietaryEvidenceKey, loading: true, error: null }));
    void verifyDietaryEvidence(
      suggestions.map((item) => item.place_id), advancedFilters.dietary, controller.signal,
    ).then((matches) => {
      if (controller.signal.aborted) return;
      setDietaryEvidence({
        key: dietaryEvidenceKey,
        loading: false,
        error: null,
        matches: new Map(matches.map((item) => [item.place_id, item.dietary_matches])),
      });
    }).catch((reason) => {
      if (controller.signal.aborted) return;
      const message = reason instanceof PlacesQuotaError
        ? "The Places limit prevented menu verification. Current results remain visible."
        : "Official-menu verification is unavailable. Current results remain visible.";
      setDietaryEvidence((current) => ({ ...current, key: dietaryEvidenceKey, loading: false, error: message }));
    });
    return () => controller.abort();
  }, [advancedFilters.dietary, dietaryEvidenceKey, dietaryRetry, suggestions]);

  const filteredSuggestions = useMemo(() => {
    const verificationReady = Boolean(advancedFilters.dietary.length) && dietaryEvidence.key === dietaryEvidenceKey && !dietaryEvidence.loading && !dietaryEvidence.error;
    const annotated = suggestions.map((place) => ({
      ...place,
      dietary_matches: verificationReady ? dietaryEvidence.matches.get(place.place_id) : place.dietary_matches,
    }));
    const effectiveAdvanced = verificationReady || !advancedFilters.dietary.length
      ? advancedFilters
      : { ...advancedFilters, dietary: [] };
    const filtered = filterSuggestions(annotated, activeFilters, effectiveAdvanced, originLocation);
    if (!preferences?.personalization_enabled) return filtered;
    const disliked = preferences.disliked_foods.map((value) => value.toLowerCase());
    const favourites = preferences.favorite_cuisines.map((value) => value.toLowerCase());
    return filtered
      .filter((place) => !disliked.some((value) => suggestionText(place).includes(value)))
      .map((place, index) => ({
        place,
        index,
        preferenceScore: favourites.filter((value) => suggestionText(place).includes(value)).length + (savedPlaceIds.has(place.place_id) ? 2 : 0),
      }))
      .sort((a, b) => b.preferenceScore - a.preferenceScore || a.index - b.index)
      .map(({ place }) => place);
  }, [activeFilters, advancedFilters, dietaryEvidence, dietaryEvidenceKey, originLocation, preferences, savedPlaceIds, suggestions]);

  const navigate = useCallback((path: string, resetChat = false) => {
    const normalized = normalizePath(path);
    if (normalized !== normalizePath(window.location.pathname)) {
      window.history.pushState({}, "", normalized);
    }
    setCurrentPath(normalized);
    setMobileMenuOpen(false);
    if (resetChat) {
      window.sessionStorage.removeItem("craveai-temporary-chat");
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
      preferences?.default_radius_meters,
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
      advancedFilters={advancedFilters}
      area={searchArea}
      canRetry={!suggestionQuotaResetAt}
      count={filteredSuggestions.length}
      error={suggestionError}
      isLoading={isLoadingSuggestions || isResolvingArea}
      onChangeLocation={() => setLocationDialogOpen(true)}
      onClearFilters={() => setActiveFilters(new Set())}
      onRetry={retrySearch}
      onToggleFilter={toggleFilter}
      onAdvancedFiltersChange={setAdvancedFilters}
      dietaryVerification={{
        loading: advancedFilters.dietary.length > 0 && (dietaryEvidence.key !== dietaryEvidenceKey || dietaryEvidence.loading),
        error: dietaryEvidence.key === dietaryEvidenceKey ? dietaryEvidence.error : null,
      }}
      onRetryDietaryVerification={() => setDietaryRetry((value) => value + 1)}
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
          ) : currentPath === "/likes" ? <LikesPage />
            : currentPath === "/history" ? <HistoryPage />
              : currentPath === "/settings" ? <SettingsPage />
                : currentPath === "/pricing" ? <PricingPage />
                  : currentPath === "/help" || currentPath.startsWith("/help/") ? <HelpPage />
                    : currentPath === "/terms" ? <LegalPage kind="terms" />
                      : currentPath === "/privacy" ? <LegalPage kind="privacy" />
                        : <PlaceholderPage content={undefined} onBack={() => navigate("/", true)} />}
        </main>
      </div>

      <LocationDialog
        onClose={() => setLocationDialogOpen(false)}
        onSelect={selectLocation}
        open={locationDialogOpen}
      />
      {user?.policy_required && currentPath !== "/terms" && currentPath !== "/privacy" ? <PolicyGate /> : null}
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

function suggestionText(place: Suggestion): string {
  return `${place.name} ${place.address || ""} ${(place.tags || []).join(" ")}`.toLowerCase();
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
