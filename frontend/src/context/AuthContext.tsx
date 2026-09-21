import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  AuthUser,
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from "../api/auth";
import { recordStartupTiming } from "../utils/startupTelemetry";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

export type AuthStatus = "checking" | "authenticated" | "guest" | "offline";

const AUTH_STARTUP_TIMEOUT_MS = 4_000;
const AUTH_RETRY_INTERVAL_MS = 15_000;

const AuthContext = createContext<AuthContextValue | null>(null);
const guestAuthFallback: AuthContextValue = {
  user: null,
  loading: false,
  status: "guest",
  login: async () => { throw new Error("Authentication provider is unavailable."); },
  logout: async () => undefined,
  refresh: async () => undefined,
};

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<AuthStatus>("checking");

  const resolveSession = useCallback(async (showLoading: boolean) => {
    const startedAt = performance.now();
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), AUTH_STARTUP_TIMEOUT_MS);
    if (showLoading) {
      setLoading(true);
      setStatus("checking");
    }
    try {
      const nextUser = await fetchCurrentUser(controller.signal);
      setUser(nextUser);
      setStatus(nextUser ? "authenticated" : "guest");
      recordStartupTiming("auth_me", "success", performance.now() - startedAt);
    } catch {
      setUser(null);
      setStatus("offline");
      recordStartupTiming(
        "auth_me",
        controller.signal.aborted ? "timeout" : "error",
        performance.now() - startedAt,
      );
    } finally {
      window.clearTimeout(timeout);
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await resolveSession(true);
  }, [resolveSession]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (status !== "offline") return;
    const retry = window.setInterval(() => {
      void resolveSession(false);
    }, AUTH_RETRY_INTERVAL_MS);
    return () => window.clearInterval(retry);
  }, [resolveSession, status]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      status,
      login: async (email, password) => {
        setUser(await loginRequest(email, password));
        setStatus("authenticated");
      },
      logout: async () => {
        await logoutRequest();
        window.sessionStorage.removeItem("craveai-temporary-chat");
        setUser(null);
        setStatus("guest");
      },
      refresh,
    }),
    [loading, refresh, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  return context || guestAuthFallback;
}
