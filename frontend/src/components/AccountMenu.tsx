import { useState } from "react";

import { useAuth } from "../context/AuthContext";

export function AccountMenu(): JSX.Element {
  const { user, loading, logout } = useAuth();
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  const confirmSignOut = async (): Promise<void> => {
    setIsSigningOut(true);
    setSignOutError(null);
    try {
      await logout();
      setShowSignOutConfirm(false);
    } catch {
      setSignOutError("We couldn't sign you out. Please try again.");
    } finally {
      setIsSigningOut(false);
    }
  };

  if (loading) {
    return <span className="text-sm text-muted-foreground">Checking account…</span>;
  }
  if (!user) {
    return (
      <a
        href="/login"
        className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
      >
        Sign in
      </a>
    );
  }
  return (
    <div className="flex min-w-0 items-center gap-3">
      <a className="truncate text-sm text-muted-foreground hover:text-foreground" href="/account">
        {user.email}
      </a>
      <button
        type="button"
        className="shrink-0 whitespace-nowrap rounded-full border border-border px-4 py-2 text-sm"
        onClick={() => {
          setSignOutError(null);
          setShowSignOutConfirm(true);
        }}
      >
        Sign out
      </button>
      {showSignOutConfirm ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          role="presentation"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !isSigningOut) {
              setShowSignOutConfirm(false);
            }
          }}
        >
          <div
            aria-describedby="sign-out-description"
            aria-labelledby="sign-out-title"
            aria-modal="true"
            className="w-full max-w-sm rounded-2xl border border-border bg-background p-6 text-foreground shadow-xl"
            role="alertdialog"
          >
            <h2 className="text-xl font-semibold" id="sign-out-title">
              Sign out of CraveAI?
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground" id="sign-out-description">
              You’ll need to sign in again to access your account and saved preferences.
            </p>
            {signOutError ? (
              <p className="mt-3 text-sm text-destructive" role="alert">
                {signOutError}
              </p>
            ) : null}
            <div className="mt-6 flex justify-end gap-3">
              <button
                autoFocus
                type="button"
                className="rounded-full border border-border px-4 py-2 text-sm font-medium"
                disabled={isSigningOut}
                onClick={() => setShowSignOutConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-full bg-foreground px-4 py-2 text-sm font-semibold text-background disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSigningOut}
                onClick={() => void confirmSignOut()}
              >
                {isSigningOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
