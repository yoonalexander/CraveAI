import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  deleteAccount,
  exportAccount,
  forgotPassword,
  googleLoginUrl,
  Identity,
  listIdentities,
  register,
  resetPassword,
  startGoogleLink,
  unlinkGoogle,
} from "../api/auth";
import { useAuth } from "../context/AuthContext";
import { fetchLegalCurrent, LegalCurrent } from "../api/product";
import { ThemeProvider } from "../context/ThemeContext";
import { ThemeToggle } from "./ThemeToggle";

type PageMode =
  | "login"
  | "register"
  | "forgot"
  | "reset"
  | "result"
  | "account";

export function AuthPage({ mode }: { mode: PageMode }): JSX.Element {
  return (
    <ThemeProvider defaultTheme="light" storageKey="craveai-theme">
      <div className="min-h-screen bg-background px-6 py-10 text-foreground">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <a href="/" className="text-sm font-bold uppercase tracking-[0.32em] text-primary">
            craveai
          </a>
          <ThemeToggle />
        </div>
        <div className="mx-auto mt-12 max-w-md rounded-3xl border border-border bg-secondary/10 p-8 shadow-xl">
          {mode === "account" ? <AccountPanel /> : <AuthForm mode={mode} />}
        </div>
      </div>
    </ThemeProvider>
  );
}

function AuthForm({ mode }: { mode: Exclude<PageMode, "account"> }): JSX.Element {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [legal, setLegal] = useState<LegalCurrent | null>(null);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acknowledgePrivacy, setAcknowledgePrivacy] = useState(false);
  const [ageConfirmed, setAgeConfirmed] = useState(false);

  useEffect(() => {
    if (mode === "register") void fetchLegalCurrent().then(setLegal).catch(() => setLegal(null));
  }, [mode]);

  const result = useMemo(
    () => new URLSearchParams(window.location.search).get("status"),
    [],
  );
  if (mode === "result") {
    return (
      <div>
        <h1 className="text-2xl font-semibold">Account status</h1>
        <p className="mt-4 text-muted-foreground">
          {result === "verified"
            ? "Your email is verified and you are signed in."
            : result === "link_required"
              ? "That email already has an account. Sign in first, then connect Google from Account."
              : "The authentication link was invalid or expired. Please try again."}
        </p>
        <a className="mt-6 inline-block text-primary underline" href="/">
          Return to CraveAI
        </a>
      </div>
    );
  }

  const title = {
    login: "Welcome back",
    register: "Create your account",
    forgot: "Reset your password",
    reset: "Choose a new password",
  }[mode];

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "login") {
        await login(email, password);
        window.location.assign("/");
      } else if (mode === "register") {
        if (!legal || !acceptTerms || !acknowledgePrivacy || !ageConfirmed) {
          throw new Error("You must accept the current policies and confirm you are 18 or older.");
        }
        await register(email, password, {
          terms_version: legal.terms.version,
          privacy_version: legal.privacy.version,
        });
        setMessage("Check your inbox to verify your email.");
      } else if (mode === "forgot") {
        await forgotPassword(email);
        setMessage("If that account exists, a recovery email is on its way.");
      } else {
        await resetPassword(password);
        setMessage("Password updated. You can now sign in.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {mode === "register"
          ? "Save favorites and receive a higher daily recommendation limit."
          : "Your credentials are handled by Supabase and never stored by CraveAI."}
      </p>
      <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
        {mode !== "reset" && (
          <label className="block text-sm">
            Email
            <input
              required
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-3"
            />
          </label>
        )}
        {!["forgot"].includes(mode) && (
          <label className="block text-sm">
            Password
            <input
              required
              type="password"
              minLength={12}
              maxLength={128}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-3"
            />
            {mode !== "login" && (
              <span className="mt-1 block text-xs text-muted-foreground">
                Use at least 12 characters.
              </span>
            )}
          </label>
        )}
        {mode === "register" ? (
          <fieldset className="space-y-3 rounded-xl border border-border p-4 text-sm">
            <legend className="px-1 font-semibold">Legal acknowledgments</legend>
            <label className="flex gap-2">
              <input checked={acceptTerms} onChange={(event) => setAcceptTerms(event.target.checked)} required type="checkbox" />
              <span>I agree to the <a className="underline" href="/terms" target="_blank">Terms and Conditions</a>.</span>
            </label>
            <label className="flex gap-2">
              <input checked={acknowledgePrivacy} onChange={(event) => setAcknowledgePrivacy(event.target.checked)} required type="checkbox" />
              <span>I acknowledge the <a className="underline" href="/privacy" target="_blank">Privacy Policy</a>.</span>
            </label>
            <label className="flex gap-2">
              <input checked={ageConfirmed} onChange={(event) => setAgeConfirmed(event.target.checked)} required type="checkbox" />
              <span>I confirm that I am 18 years of age or older.</span>
            </label>
          </fieldset>
        ) : null}
        <button
          disabled={busy || (mode === "register" && !legal)}
          className="w-full rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground disabled:opacity-60"
        >
          {busy ? "Working…" : title}
        </button>
      </form>
      {["login", "register"].includes(mode) && (
        <>
          <div className="my-5 flex items-center gap-4 text-sm text-foreground/60">
            <span className="h-px flex-1 bg-foreground/20" />
            <span>or</span>
            <span className="h-px flex-1 bg-foreground/20" />
          </div>
          <a
            href={googleLoginUrl()}
            className="flex w-full items-center justify-center gap-3 rounded-full border border-[#747775] bg-white px-4 py-3 text-sm font-medium text-[#1f1f1f] transition-colors hover:bg-[#f8fafd] focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
          >
            <GoogleLogo />
            Continue with Google
          </a>
        </>
      )}
      {message && <p className="mt-4 text-sm text-primary">{message}</p>}
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      <nav className="mt-6 flex flex-wrap gap-4 text-sm text-muted-foreground">
        {mode !== "login" && <a href="/login">Sign in</a>}
        {mode !== "register" && <a href="/register">Create account</a>}
        {mode === "login" && <a href="/forgot-password">Forgot password?</a>}
      </nav>
    </div>
  );
}

function GoogleLogo(): JSX.Element {
  return (
    <svg
      aria-hidden="true"
      className="h-[18px] w-[18px] shrink-0"
      viewBox="0 0 18 18"
    >
      <path
        fill="#4285F4"
        d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.482h4.844a4.14 4.14 0 0 1-1.797 2.716v2.258h2.909c1.703-1.568 2.684-3.878 2.684-6.615Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.468-.806 5.956-2.18l-2.909-2.258c-.806.54-1.835.859-3.047.859-2.344 0-4.328-1.585-5.037-3.714H.956v2.333A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.963 10.707A5.413 5.413 0 0 1 3.682 9c0-.592.102-1.168.281-1.707V4.96H.956A9 9 0 0 0 0 9c0 1.452.347 2.827.956 4.04l3.007-2.333Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.507.454 3.44 1.345l2.582-2.582C13.464.892 11.426 0 9 0A9 9 0 0 0 .956 4.96l3.007 2.333C4.672 5.165 6.656 3.58 9 3.58Z"
      />
    </svg>
  );
}

function AccountPanel(): JSX.Element {
  const { user, loading, logout } = useAuth();
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      void listIdentities().then(setIdentities).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "Unable to load identities.");
      });
    }
  }, [user]);

  if (loading) return <p>Loading account…</p>;
  if (!user) {
    return (
      <p>
        Please <a className="text-primary underline" href="/login">sign in</a>.
      </p>
    );
  }

  async function downloadExport(): Promise<void> {
    try {
      const data = await exportAccount();
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "craveai-account-export.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Export failed.");
    }
  }

  async function removeAccount(): Promise<void> {
    if (!window.confirm("Permanently delete your CraveAI account and saved data?")) return;
    try {
      await deleteAccount();
      window.location.assign("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Deletion failed.");
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Your account</h1>
      <p className="mt-2 text-sm text-muted-foreground">{user.email}</p>
      <section className="mt-6">
        <h2 className="font-semibold">Sign-in methods</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {identities.map((identity) => (
            <li key={identity.id} className="flex items-center justify-between rounded-xl border border-border p-3">
              <span className="capitalize">{identity.provider}</span>
              {identity.provider === "google" && identities.length > 1 && (
                <button onClick={() => void unlinkGoogle(identity.id)}>Disconnect</button>
              )}
            </li>
          ))}
        </ul>
        {!identities.some((identity) => identity.provider === "google") && (
          <button className="mt-3 text-sm text-primary underline" onClick={() => void startGoogleLink()}>
            Connect Google
          </button>
        )}
      </section>
      <div className="mt-8 space-y-3">
        <button className="w-full rounded-xl border border-border px-4 py-3" onClick={() => void downloadExport()}>
          Download my data
        </button>
        <button className="w-full rounded-xl border border-border px-4 py-3" onClick={() => void logout()}>
          Sign out
        </button>
        <button className="w-full rounded-xl border border-red-500 px-4 py-3 text-red-600" onClick={() => void removeAccount()}>
          Delete account
        </button>
      </div>
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
    </div>
  );
}
