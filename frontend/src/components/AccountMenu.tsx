import { useEffect, useRef, useState } from "react";

import { useAuth } from "../context/AuthContext";
import { accountName } from "../api/auth";
import { UserIcon } from "./Icons";

export function AccountMenu(): JSX.Element {
  const { user, loading, logout, status } = useAuth();
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const signOutButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showSignOutConfirm) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const trigger = signOutButtonRef.current;
    return () => trigger?.focus();
  }, [showSignOutConfirm]);

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
  if (status === "offline") {
    return <span className="text-sm text-muted-foreground">Account unavailable — retrying…</span>;
  }
  if (!user) {
    return (
      <div className="top-auth-actions">
        <a className="top-login-button" href="/login">Log in</a>
        <a className="top-signup-button" href="/register">Sign up for free</a>
      </div>
    );
  }
  return (
    <div className="top-auth-actions signed-in-actions">
      <a
        className="top-profile-button"
        href="/account"
        aria-label={`Account: ${accountName(user)}`}
        title={`Account: ${accountName(user)}`}
      >
        <UserIcon />
      </a>
      <button
        ref={signOutButtonRef}
        type="button"
        className="top-signout-button shrink-0 whitespace-nowrap"
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
            if (event.key === "Tab") {
              const buttons = dialogRef.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])");
              if (!buttons?.length) { event.preventDefault(); return; }
              const target = event.shiftKey ? buttons[buttons.length - 1] : buttons[0];
              const boundary = event.shiftKey ? buttons[0] : buttons[buttons.length - 1];
              if (document.activeElement === boundary) {
                event.preventDefault();
                target.focus();
              }
            }
          }}
        >
          <div
            ref={dialogRef}
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
