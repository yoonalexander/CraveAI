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

type PageMode =
  | "login"
  | "register"
  | "forgot"
  | "reset"
  | "result"
  | "account";

export function AuthPage({ mode }: { mode: PageMode }): JSX.Element {
  const accountPrompt = mode === "register"
    ? { label: "Already have an account?", href: "/login", action: "Log in" }
    : { label: "New to CraveAI?", href: "/register", action: "Sign up for free" };

  return (
    <div className={`auth-page auth-page-${mode}`}>
      <header className="auth-header">
        <a href="/" className="auth-brand" aria-label="CraveAI home">
          <img alt="" src="/craveai-pin.svg" />
          <span>CRAVEAI</span>
        </a>
        {mode !== "account" && mode !== "result" ? (
          <div className="auth-header-prompt">
            <span>{accountPrompt.label}</span>
            <a href={accountPrompt.href}>{accountPrompt.action}</a>
          </div>
        ) : (
          <a className="auth-home-link" href="/">Back to CraveAI</a>
        )}
      </header>

      <main className="auth-layout">
        <AuthShowcase mode={mode} />
        <section className="auth-card" aria-label={mode === "account" ? "Account" : "Authentication"}>
          {mode === "account" ? <AccountPanel /> : <AuthForm mode={mode} />}
        </section>
      </main>

      <nav aria-label="Legal" className="auth-legal-nav">
        <span>© {new Date().getFullYear()} CraveAI</span>
        <a href="/terms">Terms of Service</a>
        <a href="/privacy">Privacy Policy</a>
        <a href="/help/data-use">Data use</a>
      </nav>
    </div>
  );
}

function AuthShowcase({ mode }: { mode: PageMode }): JSX.Element {
  const isAccount = mode === "account";
  return (
    <section className="auth-showcase" aria-label="About CraveAI">
      <p className="auth-eyebrow">Personalized restaurant discovery</p>
      <h2>{isAccount ? "Your CraveAI, under your control." : "A better answer to “where should we eat?”"}</h2>
      <p className="auth-showcase-copy">
        {isAccount
          ? "Manage your sign-in methods and account data from one clear, private place."
          : "Tell us what sounds good. CraveAI searches the area you choose and brings back grounded restaurant recommendations."}
      </p>
      <div className="auth-preview" aria-hidden="true">
        <div className="auth-preview-map">
          <span className="auth-preview-road auth-preview-road-one" />
          <span className="auth-preview-road auth-preview-road-two" />
          <span className="auth-preview-road auth-preview-road-three" />
          <span className="auth-preview-pin auth-preview-pin-one"><b>★ 4.7</b></span>
          <span className="auth-preview-pin auth-preview-pin-two"><b>★ 4.5</b></span>
          <span className="auth-preview-you" />
        </div>
        <div className="auth-preview-result">
          <span className="auth-preview-kicker">A cozy match nearby</span>
          <strong>Great food, picked for your craving</strong>
          <span>Grounded in location, ratings, and live restaurant data.</span>
        </div>
      </div>
      <div className="auth-trust-row">
        <span>Map-aware</span>
        <span>Preference-ready</span>
        <span>Privacy controls</span>
      </div>
    </section>
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
      <div className="auth-form auth-result">
        <p className="auth-eyebrow">Account update</p>
        <h1 className="auth-title">Account status</h1>
        <p className="auth-subtitle">
          {result === "verified"
            ? "Your email is verified and you are signed in."
            : result === "link_required"
              ? "That email already has an account. Sign in first, then connect Google from Account."
              : "The authentication link was invalid or expired. Please try again."}
        </p>
        <a className="auth-text-link auth-result-link" href="/">
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
  const buttonLabel = {
    login: "Log in",
    register: "Sign up for free",
    forgot: "Send reset link",
    reset: "Update password",
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
    <div className="auth-form">
      <p className="auth-eyebrow">{mode === "register" ? "Start discovering" : "Welcome to CraveAI"}</p>
      <h1 className="auth-title">{title}</h1>
      <p className="auth-subtitle">
        {mode === "register"
          ? "Save favorites and receive a higher daily recommendation limit."
          : "Your credentials are handled by Supabase and never stored by CraveAI."}
      </p>
      <form className="auth-fields" onSubmit={(event) => void submit(event)}>
        {mode !== "reset" && (
          <label className="auth-field">
            Email
            <input
              required
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="auth-input"
              placeholder="you@example.com"
            />
          </label>
        )}
        {!["forgot"].includes(mode) && (
          <label className="auth-field">
            Password
            <input
              required
              type="password"
              minLength={12}
              maxLength={128}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="auth-input"
            />
            {mode !== "login" && (
              <span className="auth-field-hint">
                Use at least 12 characters.
              </span>
            )}
          </label>
        )}
        {mode === "register" ? (
          <fieldset className="auth-legal-box">
            <legend>Legal acknowledgments</legend>
            <label>
              <input checked={acceptTerms} onChange={(event) => setAcceptTerms(event.target.checked)} required type="checkbox" />
              <span>I agree to the <a href="/terms" target="_blank">Terms of Service</a>.</span>
            </label>
            <label>
              <input checked={acknowledgePrivacy} onChange={(event) => setAcknowledgePrivacy(event.target.checked)} required type="checkbox" />
              <span>I acknowledge the <a href="/privacy" target="_blank">Privacy Policy</a>.</span>
            </label>
            <label>
              <input checked={ageConfirmed} onChange={(event) => setAgeConfirmed(event.target.checked)} required type="checkbox" />
              <span>I confirm that I am 18 years of age or older.</span>
            </label>
          </fieldset>
        ) : null}
        <button
          disabled={busy || (mode === "register" && !legal)}
          className="auth-primary-button"
        >
          {busy ? "Working…" : buttonLabel}
        </button>
      </form>
      {["login", "register"].includes(mode) && (
        <>
          <div className="auth-divider">
            <span className="h-px flex-1 bg-foreground/20" />
            <span>or</span>
            <span className="h-px flex-1 bg-foreground/20" />
          </div>
          <a
            href={googleLoginUrl()}
            className="auth-google-button"
          >
            <GoogleLogo />
            Continue with Google
          </a>
        </>
      )}
      {message && <p className="auth-message" role="status">{message}</p>}
      {error && <p className="auth-error" role="alert">{error}</p>}
      <nav className="auth-switch-links">
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

  if (loading) return <p className="auth-subtitle">Loading account…</p>;
  if (!user) {
    return (
      <p className="auth-subtitle">
        Please <a className="auth-text-link" href="/login">sign in</a>.
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
    <div className="auth-form account-form">
      <p className="auth-eyebrow">Account</p>
      <h1 className="auth-title">Your account</h1>
      <p className="auth-subtitle">{user.email}</p>
      <section className="account-section">
        <h2>Sign-in methods</h2>
        <ul className="account-identities">
          {identities.map((identity) => (
            <li key={identity.id}>
              <span>{identity.provider}</span>
              {identity.provider === "google" && identities.length > 1 && (
                <button className="auth-text-link" onClick={() => void unlinkGoogle(identity.id)}>Disconnect</button>
              )}
            </li>
          ))}
        </ul>
        {!identities.some((identity) => identity.provider === "google") && (
          <button className="auth-text-link account-connect" onClick={() => void startGoogleLink()}>
            Connect Google
          </button>
        )}
      </section>
      <div className="account-actions">
        <button className="auth-secondary-button" onClick={() => void downloadExport()}>
          Download my data
        </button>
        <button className="auth-secondary-button" onClick={() => void logout()}>
          Sign out
        </button>
        <button className="auth-danger-button" onClick={() => void removeAccount()}>
          Delete account
        </button>
      </div>
      {error && <p className="auth-error" role="alert">{error}</p>}
    </div>
  );
}
