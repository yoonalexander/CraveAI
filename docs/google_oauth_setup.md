# Google sign-in setup

CraveAI uses a full-page OAuth redirect, not a popup. The browser follows this
route:

1. CraveAI frontend: `/login`
2. CraveAI backend: `/api/auth/google/start`
3. Supabase Auth
4. Google Accounts
5. Supabase Auth callback
6. CraveAI backend: `/api/auth/google/callback`
7. CraveAI frontend: `/`

The Google Accounts URL contains short-lived state and PKCE values. Never copy,
store, or hard-code a URL from the browser address bar.

## 1. Configure Google Auth Platform

In the Google Cloud project used for CraveAI:

1. Open **Google Auth Platform > Branding** and set the app name, support email,
   homepage, privacy-policy URL, terms URL, and authorized domain.
2. Under **Audience**, select the appropriate audience. While the app is in
   Testing, add every Google account that should be able to sign in.
3. Under **Data Access**, request only:
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
4. Under **Clients**, create an OAuth client with application type
   **Web application**.
5. Add the frontend origins:
   - `http://localhost:5173`
   - `https://<production-frontend-domain>`
6. Add this **Authorized redirect URI**:

   ```text
   https://gyrxxvxsguwugqueuaav.supabase.co/auth/v1/callback
   ```

   This is the Supabase provider callback. Do not put CraveAI's
   `/api/auth/google/callback` URL in the Google Cloud redirect-URI field.
7. Copy the generated client ID and client secret into the Google provider
   settings in Supabase. Do not put the client secret in frontend code or in
   this repository.

## 2. Configure Supabase Auth

In the Supabase project:

1. Open **Authentication > Providers > Google**.
2. Enable Google, paste the Google client ID and client secret, then save.
3. Open **Authentication > URL Configuration**.
4. Set **Site URL** to the production frontend origin.
5. Add these exact redirect URLs:

   ```text
   http://localhost:5173/api/auth/confirm
   http://localhost:5173/api/auth/password/recovery
   http://localhost:5173/api/auth/google/callback
   https://<production-frontend-domain>/api/auth/confirm
   https://<production-frontend-domain>/api/auth/password/recovery
   https://<production-frontend-domain>/api/auth/google/callback
   ```

   Use exact production URLs rather than a broad wildcard.
6. Open the general Auth configuration and enable **Manual Linking**. CraveAI
   requires an existing password account to sign in before connecting a Google
   identity with the same email address.

There are two different callback settings by design:

| Console | Callback |
| --- | --- |
| Google Cloud | `https://<project-ref>.supabase.co/auth/v1/callback` |
| Supabase redirect allowlist | `https://<frontend-domain>/api/auth/google/callback` |

## 3. Configure CraveAI

For local development, set the values documented in `.env.example`. At minimum,
authentication needs:

```text
SUPABASE_URL=https://gyrxxvxsguwugqueuaav.supabase.co
SUPABASE_ANON_KEY=<server-side secret-store value>
SUPABASE_SERVICE_ROLE_KEY=<server-side secret-store value>
SESSION_ENCRYPTION_KEY=<generated Fernet key>
IDENTITY_SIGNING_SECRET=<at least 32 random characters>
FRONTEND_ORIGIN=http://localhost:5173
PUBLIC_API_URL=http://localhost:5173/api
ALLOWED_ORIGINS=http://localhost:5173
```

In production, `FRONTEND_ORIGIN` must be the public frontend origin and
`PUBLIC_API_URL` must be that same origin plus `/api`. The Vercel rewrite then
proxies the callback to Render while cookies remain first-party to the frontend
domain. Do not set `VITE_API_URL` to the Render service URL. For local
development against a deployed backend, set `VITE_DEV_API_TARGET` to Render and
continue to let the browser use `/api`.

## 4. Verify

1. Start the backend and frontend.
2. Visit `http://localhost:5173/login`.
3. Select **Continue with Google**.
4. Confirm that Google opens in the same browser tab.
5. Complete sign-in and confirm that the browser returns to `/`.
6. Visit `/account` and confirm that `google` appears under sign-in methods.
7. Repeat on the production domain with a Google test user before publishing
   the OAuth app.

Google controls the layout of the Accounts page. A wide full-tab window usually
uses the two-column layout, while a narrow window uses the compact layout.
CraveAI can configure its name, logo, domains, and requested scopes, but it
cannot customize Google's page structure.

## Troubleshooting

- **`/api/auth/google/start` returns 404:** deploy a backend revision that
  includes the `/api/auth/*` routes. Confirm them in the deployed
  `/openapi.json` before debugging Google settings.
- **`redirect_uri_mismatch` on Google:** the Google Cloud OAuth client's
  redirect URI is wrong. It must be the Supabase `/auth/v1/callback` URL.
- **Supabase redirects to the Site URL instead of CraveAI's callback:** add the
  exact CraveAI `/api/auth/google/callback` URL to Supabase's redirect
  allowlist.
- **Google says the app is unavailable or access is blocked:** while the OAuth
  app is in Testing, add the account under Google Auth Platform **Audience >
  Test users**.
- **Google completes but CraveAI reports an invalid transaction:** verify that
  the browser is using same-origin `/api`, `PUBLIC_API_URL` points to the
  frontend domain plus `/api`, and no `VITE_API_URL` override points directly
  to Render.

Official references:

- [Supabase: Login with Google](https://supabase.com/docs/guides/auth/social-login/auth-google)
- [Supabase: Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Google: Sign in with Google branding](https://developers.google.com/identity/branding-guidelines)
