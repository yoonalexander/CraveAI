import { ComponentType, useEffect, useRef } from "react";

import type { CurrentWeather } from "../api/weather";
import { useAuth } from "../context/AuthContext";
import {
  BadgeIcon,
  CloudIcon,
  CompassIcon,
  HeartIcon,
  HelpIcon,
  HistoryIcon,
  PanelIcon,
  PenIcon,
  SettingsIcon,
  SunIcon,
  UserIcon,
} from "./Icons";

type SidebarProps = {
  collapsed: boolean;
  currentPath: string;
  mobileOpen: boolean;
  weather: CurrentWeather | null;
  weatherLoading: boolean;
  onCloseMobile: () => void;
  onNavigate: (path: string, resetChat?: boolean) => void;
  onToggle: () => void;
};

type NavigationItem = {
  label: string;
  path: string;
  icon: ComponentType<{ className?: string }>;
  resetChat?: boolean;
};

const primaryItems: NavigationItem[] = [
  { label: "New chat", path: "/", icon: PenIcon, resetChat: true },
  { label: "Discovery", path: "/discovery", icon: CompassIcon },
  { label: "Likes", path: "/likes", icon: HeartIcon },
  { label: "History", path: "/history", icon: HistoryIcon },
];

const secondaryItems: NavigationItem[] = [
  { label: "See plans and pricing", path: "/pricing", icon: BadgeIcon },
  { label: "Settings", path: "/settings", icon: SettingsIcon },
  { label: "Help", path: "/help", icon: HelpIcon },
];

export function Sidebar({
  collapsed,
  currentPath,
  mobileOpen,
  weather,
  weatherLoading,
  onCloseMobile,
  onNavigate,
  onToggle,
}: SidebarProps): JSX.Element {
  const { user } = useAuth();
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;
    document.body.classList.add("crave-overlay-open");
    const panel = panelRef.current;
    const focusable = panel?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    focusable?.[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCloseMobile();
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
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
  }, [mobileOpen, onCloseMobile]);

  const navigate = (
    event: React.MouseEvent<HTMLAnchorElement>,
    item: NavigationItem,
  ) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    onNavigate(item.path, item.resetChat);
    onCloseMobile();
  };

  const renderItem = (item: NavigationItem) => {
    const Icon = item.icon;
    const active = currentPath === item.path;
    return (
      <a
        aria-current={active ? "page" : undefined}
        className={`sidebar-link${active ? " is-active" : ""}`}
        href={item.path}
        key={item.path}
        onClick={(event) => navigate(event, item)}
        title={collapsed ? item.label : undefined}
      >
        <Icon className="sidebar-icon" />
        <span className="sidebar-label">{item.label}</span>
      </a>
    );
  };

  return (
    <>
      <button
        aria-label="Close navigation"
        className={`sidebar-scrim${mobileOpen ? " is-open" : ""}`}
        onClick={onCloseMobile}
        tabIndex={mobileOpen ? 0 : -1}
        type="button"
      />
      <aside
        aria-label="Main navigation"
        className={`crave-sidebar${collapsed ? " is-collapsed" : ""}${mobileOpen ? " is-mobile-open" : ""}`}
        ref={panelRef}
      >
        <div className="sidebar-top">
          <img alt="CraveAI" className="sidebar-logo" src="/craveai-pin.svg" />
          <button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="sidebar-collapse-button"
            onClick={onToggle}
            onPointerUp={(event) => event.currentTarget.blur()}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            type="button"
          >
            <PanelIcon className="sidebar-icon" />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="CraveAI">
          {primaryItems.map(renderItem)}
        </nav>

        <div
          className="sidebar-weather"
          title={weather ? `${Math.round(weather.temperature)}°C ${weather.condition}` : "Weather unavailable"}
        >
          {weather?.condition === "Clear" ? (
            <SunIcon className="sidebar-weather-icon is-sunny" />
          ) : (
            <CloudIcon className="sidebar-weather-icon" />
          )}
          <div className="sidebar-weather-copy">
            <strong>
              {weatherLoading
                ? "—"
                : weather
                  ? `${Math.round(weather.temperature)}°C`
                  : "—"}
            </strong>
            <span>
              {weatherLoading
                ? "Checking weather"
                : weather?.condition || "Weather unavailable"}
            </span>
            {weather ? <a className="weather-attribution" href="https://open-meteo.com/" rel="noreferrer" target="_blank">Weather by Open-Meteo</a> : null}
          </div>
        </div>

        <div className="sidebar-spacer" />
        <nav className="sidebar-nav sidebar-nav-secondary" aria-label="Support">
          {secondaryItems.map(renderItem)}
        </nav>

        <div className="sidebar-account">
          {user ? (
            <a
              className="sidebar-account-link"
              href="/account"
              title={collapsed ? "Account" : undefined}
            >
              <UserIcon className="sidebar-icon" />
              <span className="sidebar-account-copy">
                <strong>Your account</strong>
                <small>{user.email}</small>
              </span>
            </a>
          ) : (
            <>
              <div className="sidebar-login-copy">
                <strong>Get responses tailored to you</strong>
                <p>Log in to save spots and get answers based on your preferences.</p>
              </div>
              <a className="sidebar-login-button" href="/login">
                <UserIcon className="sidebar-icon sidebar-login-icon" />
                <span>Log in</span>
              </a>
            </>
          )}
        </div>
        <nav aria-label="Legal" className="sidebar-legal-links">
          <a href="/terms">Terms</a>
          <a href="/privacy">Privacy</a>
        </nav>
      </aside>
    </>
  );
}
