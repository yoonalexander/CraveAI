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

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const guestAuthFallback: AuthContextValue = {
  user: null,
  loading: false,
  login: async () => { throw new Error("Authentication provider is unavailable."); },
  logout: async () => undefined,
  refresh: async () => undefined,
};

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await fetchCurrentUser());
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        setUser(await loginRequest(email, password));
      },
      logout: async () => {
        await logoutRequest();
        window.sessionStorage.removeItem("craveai-temporary-chat");
        setUser(null);
      },
      refresh,
    }),
    [loading, refresh, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  return context || guestAuthFallback;
}
