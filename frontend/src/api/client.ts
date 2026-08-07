// Authentication relies on first-party cookies, so browser requests must stay
// on the frontend origin and pass through the Vite/Vercel /api proxy.
export const API_BASE = "/api";

let csrfToken: string | null = null;

export function clearCsrfToken(): void {
  csrfToken = null;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
  options: { csrf?: boolean } = {},
): Promise<Response> {
  const method = (init.method || "GET").toUpperCase();
  const needsCsrf =
    options.csrf ?? !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers = new Headers(init.headers);
  if (needsCsrf) {
    headers.set("X-CSRF-Token", await getCsrfToken());
  }
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${API_BASE}/auth/csrf`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("Sign in is required for this action.");
  }
  const body = (await response.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

export async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?: { code?: string } | string;
    };
    if (typeof body.detail === "string") return body.detail;
    return body.detail?.code?.replaceAll("_", " ") || "Request failed.";
  } catch {
    return "Request failed.";
  }
}
