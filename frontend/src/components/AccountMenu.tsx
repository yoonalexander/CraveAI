import { useAuth } from "../context/AuthContext";

export function AccountMenu(): JSX.Element {
  const { user, loading, logout } = useAuth();

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
    <div className="flex items-center gap-3">
      <a className="text-sm text-muted-foreground hover:text-foreground" href="/account">
        {user.email}
      </a>
      <button
        type="button"
        className="rounded-full border border-border px-4 py-2 text-sm"
        onClick={() => void logout()}
      >
        Sign out
      </button>
    </div>
  );
}
