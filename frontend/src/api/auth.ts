import { API_BASE, apiFetch, clearCsrfToken, readApiError } from "./client";

export type AuthUser = {
  user_id: string;
  email: string;
  email_verified: boolean;
};

export type Identity = {
  id: string;
  provider: string;
  email?: string | null;
};

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const response = await apiFetch("/auth/me", {}, { csrf: false });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { user: AuthUser }).user;
}

export async function register(email: string, password: string): Promise<void> {
  await authPost("/auth/register", { email, password });
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const response = await apiFetch(
    "/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    },
    { csrf: false },
  );
  if (!response.ok) throw new Error(await readApiError(response));
  clearCsrfToken();
  return ((await response.json()) as { user: AuthUser }).user;
}

export async function logout(): Promise<void> {
  const response = await apiFetch("/auth/logout", { method: "POST" });
  if (!response.ok) throw new Error(await readApiError(response));
  clearCsrfToken();
}

export async function forgotPassword(email: string): Promise<void> {
  await authPost("/auth/password/forgot", { email });
}

export async function resetPassword(password: string): Promise<void> {
  const response = await apiFetch(
    "/auth/password/reset",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    },
    { csrf: false },
  );
  if (!response.ok) throw new Error(await readApiError(response));
  clearCsrfToken();
}

export function googleLoginUrl(): string {
  return `${API_BASE}/auth/google/start`;
}

export async function listIdentities(): Promise<Identity[]> {
  const response = await apiFetch("/auth/identities", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function startGoogleLink(): Promise<void> {
  const response = await apiFetch("/auth/identities/google/link", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await readApiError(response));
  const body = (await response.json()) as { authorization_url: string };
  window.location.assign(body.authorization_url);
}

export async function unlinkGoogle(identityId: string): Promise<void> {
  const response = await apiFetch(
    `/auth/identities/google?identity_id=${encodeURIComponent(identityId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function exportAccount(): Promise<unknown> {
  const response = await apiFetch("/account/export", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function deleteAccount(): Promise<void> {
  const response = await apiFetch("/account", { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
  clearCsrfToken();
}

async function authPost(path: string, payload: unknown): Promise<void> {
  const response = await apiFetch(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    { csrf: false },
  );
  if (!response.ok) throw new Error(await readApiError(response));
}
