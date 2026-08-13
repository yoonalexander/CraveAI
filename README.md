# CraveAI

CraveAI is a React and FastAPI restaurant recommender powered by OpenAI and
Google Places. Guests can try a bounded demo; verified accounts can save
favorites, submit feedback, use higher quotas, connect Google, export their
data, and delete their account.

## Architecture

- React/Vite frontend deployed on Vercel
- FastAPI backend deployed on Render
- Supabase Auth for email/password, verification, recovery, and Google OAuth
- Supabase Postgres for profiles, opaque app sessions, favorites, feedback,
  quotas, auth transactions, and audit events
- Same-origin `/api` Vercel proxy so session cookies are first-party

Supabase access and refresh tokens never enter browser JavaScript. The backend
encrypts them and gives the browser a random `HttpOnly` application-session
cookie. Mutating account endpoints also require a session-bound CSRF token.
Chat prompts and responses are not stored.

## Local development

1. Copy `.env.example` to `.env` and fill in the required development values.
   Use separate Google keys: `GOOGLE_API_KEY` is the backend Places key, while
   `VITE_GOOGLE_MAPS_API_KEY` is a public browser key restricted by website
   referrer with Maps JavaScript, Places, and Geocoding enabled. Never reuse an
   unrestricted server key in the frontend.
2. Create the database schema:

   ```powershell
   python -m pip install -r backend\requirements.txt
   alembic upgrade head
   ```

3. Start the backend:

   ```powershell
   uvicorn backend.main:create_app --factory --reload
   ```

4. Start the frontend in another terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Vite proxies `/api` to `VITE_DEV_API_TARGET`, which defaults to
`http://127.0.0.1:8000`.

## Authentication setup

The Supabase project URL is prefilled as
`https://gyrxxvxsguwugqueuaav.supabase.co`; keys are intentionally not stored in
the repository. Configure the anon and service-role keys in the backend secret
store. Configure Resend as Supabase Auth's custom SMTP provider and add these
external URLs to the Supabase redirect allowlist:

- `${PUBLIC_API_URL}/auth/confirm`
- `${PUBLIC_API_URL}/auth/password/recovery`
- `${PUBLIC_API_URL}/auth/google/callback`

See [security operations](docs/security_operations.md) for production setup,
rotation, retention, and incident procedures. For the exact Google Cloud and
Supabase callback configuration, see
[Google sign-in setup](docs/google_oauth_setup.md).

## API

Canonical routes live under `/api`:

- `POST /auth/register`, `/auth/login`, `/auth/logout`
- `GET /auth/confirm`, `/auth/me`, `/auth/csrf`
- `POST /auth/password/forgot`, `/auth/password/reset`
- `GET /auth/password/recovery`
- `GET /auth/google/start`, `/auth/google/callback`
- `GET /auth/identities`
- `POST /auth/identities/google/link`
- `DELETE /auth/identities/google`
- `GET /account/export`
- `DELETE /account`
- `POST /chat`
- `GET /places/suggestions`
- `GET`, `POST`, `DELETE /favorites`
- `POST /feedback`

The old public `/chat` and `/places/suggestions` paths remain temporary
compatibility aliases with the same quotas and controls. Caller-selected
favorite identities and public feedback writes have been removed.

## Tests

```powershell
python -m pytest -q --basetemp=.test-tmp
cd frontend
npm test
npm run lint
npm run build
```

CI additionally runs dependency audits, migration rendering, and secret
scanning. Review [SECURITY.md](SECURITY.md) before changing an authentication,
authorization, quota, logging, or data-handling boundary.
