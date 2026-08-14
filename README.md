# CraveAI

CraveAI is a location-aware restaurant recommender that turns a natural-language
food craving into nearby, evidence-backed suggestions. Its core product rule is
simple: a restaurant should be recommended because a real dish appears to match
the request—not because the restaurant is popular or merely sounds plausible.

The application combines a React/Vite client, a FastAPI API, OpenAI Structured
Outputs, Google Places, public official restaurant menu pages, Supabase Auth,
and Postgres. Guests can use a quota-limited demo. Verified accounts can save
favorites, submit feedback, connect Google, export their data, and delete their
account.

## Recommendation principles

- **Accuracy over fixed result counts:** the engine returns zero to three
  restaurants and does not fill empty slots with weak matches.
- **Dish evidence over restaurant stereotypes:** actual menu items and official
  menu-page evidence outweigh cuisine inference, ratings, and popularity.
- **Constraint-aware matching:** `must`, `need`, `maybe`, `preferably`, `not`,
  dietary needs, and other contextual language receive different treatment.
- **Coherent dishes over aggregate matches:** separate dishes cannot be combined
  to manufacture a match. A spicy roll served with plain miso soup is not a
  spicy-soup dish.
- **Grounded explanations:** every explanation is assembled from selected,
  attributable evidence. The language model cannot invent the final reason.
- **Ratings as a tie-breaker:** Google rating contributes only 5% of the final
  score and cannot rescue an irrelevant candidate.

## How recommendation works

```text
craving + location
    -> structured intent and preference strengths
    -> 2-4 dish-oriented Google Places searches
    -> merge and cap nearby restaurant candidates
    -> retrieve public official menu/order-page evidence
    -> map known evidence to known constraints
    -> deterministic constraint, coherence, and exclusion scoring
    -> confidence/evidence threshold
    -> 0-3 restaurants with matching dishes, reasons, and source links
```

The structured intent covers taste, texture, temperature, cuisine, dish type,
ingredients, diet, health goals, price, meal context, and exclusions. Required
positive constraints need official-quality evidence; strong preferences need at
least medium-quality evidence. Multi-part requests also need one coherent item
to cover at least 70% of the weighted request.

The deterministic score is:

```text
overall score = 0.82 * food relevance
              + 0.13 * evidence strength
              + 0.05 * rating quality
```

The recommendation threshold is `0.58`. Evidence quality descends from
structured official menu items, to visible official menu-page text, to a
query-specific Google Places match, to explicit restaurant tags. Provider-only
matches are labeled as unverified instead of being described as confirmed menu
items.

For the full rationale, algorithms, failure analysis, and evaluation details,
see:

- [Recommendation engine technical design](docs/technical_design.md)
- [Recommendation engine overhaul](docs/recommendation_engine_overhaul.md)

## Product features

- Natural-language craving chat with structured recommendation evidence
- Location selection using device geolocation or place search
- Google Maps display for nearby suggestions and recommendation markers
- Suggested nearby restaurants with client-side category filters
- Match score, confidence, matched/unmatched preferences, matching dishes, and
  clickable evidence sources
- Email/password registration, confirmation, login, and password recovery
- Google sign-in and explicit identity linking/unlinking
- Authenticated favorites and feedback
- Guest and account-specific daily quotas plus global provider budgets
- Account export and deletion
- Responsive light/dark interface
- Current local weather context in the frontend

## Architecture

| Layer | Implementation | Responsibility |
| --- | --- | --- |
| Frontend | React 18, TypeScript, Vite 8 | Chat, location, maps, evidence display, account UI |
| API | FastAPI, Pydantic | Validation, security boundary, quotas, orchestration |
| Intent | OpenAI Structured Outputs | Typed craving constraints and dish-oriented searches |
| Retrieval | Google Places Text Search (New) | Nearby query-specific restaurant candidates |
| Menu evidence | `httpx`, HTML/JSON-LD parser | Ephemeral evidence from public official menu/order pages |
| Ranking | Model-assisted evidence classification plus deterministic Python scoring | Constraint satisfaction, coherence, exclusions, confidence |
| Authentication | Supabase Auth | Email/password, verification, recovery, Google OAuth |
| Application data | SQLAlchemy, Alembic, Supabase Postgres | Profiles, opaque sessions, identities, favorites, feedback, quotas, audits |
| Hosting | Vercel frontend, Render backend | Same-origin `/api` proxy and backend runtime |

There is intentionally no vector database or embedding layer in the current
implementation. CraveAI does not yet have a reliable, permissioned, fresh menu
corpus to index. Embedding sparse restaurant names and tags would reproduce the
old plausibility problem rather than create real dish-level retrieval.

## Repository layout

```text
CraveAI/
|-- backend/
|   |-- main.py                         FastAPI application and security headers
|   |-- config.py                       Environment-backed configuration
|   |-- routers/                        Auth, legal, account data, chat, places, audio, feedback
|   |-- services/
|   |   |-- craving_intent.py           Typed craving extraction and local fallback
|   |   |-- restaurant_retrieval.py     Dish-oriented Places retrieval and merging
|   |   |-- menu_evidence.py            Safe official-menu retrieval and extraction
|   |   |-- evidence_ranker.py          Evidence mapping, scoring, and explanations
|   |   |-- rag_pipeline.py             Recommendation orchestration and failure handling
|   |   `-- recommendation_models.py    Shared intent/evidence schemas
|   `-- migrations/                     Alembic database schema
|-- frontend/
|   |-- src/                            React application and tests
|   `-- vercel.json                     Security headers, API proxy, SPA routing
|-- evaluation/
|   `-- craving_cases.json              20-case labeled recommendation set
|-- scripts/
|   |-- evaluate_recommendations.py      Controlled before/after quality evaluation
|   |-- benchmark_latency.py             API framework/serialization benchmark
|   `-- security_maintenance.py          Retention cleanup job
|-- tests/                               Backend, security, and quality regressions
|-- docs/                                Design, implementation, OAuth, and operations docs
|-- SECURITY.md                          Security policy and invariants
`-- .env.example                        Configuration template
```

## Prerequisites

- Python 3.11, matching `runtime.txt`
- A Node.js/npm version supported by Vite 8
- An OpenAI API key
- A backend Google Maps Platform key with the Places API enabled
- A separate browser-restricted Google Maps key for the frontend
- Supabase Auth and Postgres for production account features

For a local-only development database, synchronous SQLite is supported. Supabase
credentials are still needed to exercise real registration, login, recovery,
Google linking, or account deletion.

## Local development

### 1. Install backend dependencies

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

### 2. Install frontend dependencies

```powershell
cd frontend
npm ci
cd ..
```

### 3. Configure the environment

```powershell
Copy-Item .env.example .env
```

Fill in the provider and security values in `.env`. Important key separation:

- `GOOGLE_API_KEY` is server-side and is used for Google Places web-service
  requests.
- `VITE_GOOGLE_MAPS_API_KEY` is intentionally exposed to the browser. Restrict
  it by website referrer and enable only Maps JavaScript, Places, and Geocoding.
- Never use the backend key as the browser key.

For a disposable local SQLite database, replace the Postgres settings with:

```dotenv
DATABASE_URL=sqlite:///./data/craveai.db
AUTO_CREATE_SCHEMA=true
APP_ENV=development
```

Create the ignored local data directory once:

```powershell
New-Item -ItemType Directory -Force data | Out-Null
```

For Postgres, keep `AUTO_CREATE_SCHEMA=false` and apply the migration:

```powershell
alembic upgrade head
```

The initial migration contains Supabase-specific foreign keys and role/RLS
statements, so use it against the intended Supabase Postgres project. Automatic
schema creation is a development convenience only and is forbidden in production.

### 4. Run the backend

```powershell
uvicorn backend.main:create_app --factory --reload
```

The API is available at `http://127.0.0.1:8000`. Its OpenAPI schema is exposed
at `http://127.0.0.1:8000/openapi.json` and FastAPI registers its documentation
route at `http://127.0.0.1:8000/docs`.

### 5. Run the frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`. Vite reads environment variables from the
repository root and proxies `/api` to `VITE_DEV_API_TARGET`, which defaults to
`http://127.0.0.1:8000`.

## Chat API contract

Canonical routes are under `/api`. A minimal request is:

```http
POST /api/chat
Content-Type: application/json

{
  "query": "im craving something spicy, maybe like a soup",
  "location": {
    "lat": 43.583,
    "lng": -79.7145,
    "radius": 5000
  }
}
```

The client may also include up to 20 ephemeral `candidate_places` from its
current nearby session. They are accepted only as bounded retrieval hints; the
browser cannot supply final scores or evidence.

An abbreviated response looks like:

```json
{
  "reply": "I found 2 relevant nearby options; menu-backed matches are marked with higher confidence.",
  "recommendations": [
    {
      "place_id": "provider-place-id",
      "name": "Example Restaurant",
      "rating": 4.4,
      "address": "123 Example Street",
      "match_score": 0.91,
      "confidence": "high",
      "matching_dishes": ["Tom Yum Noodle Soup"],
      "matched_preferences": ["spicy", "soup"],
      "unmatched_preferences": [],
      "reason": "Official menu evidence: Tom Yum Noodle Soup. Matches spicy, soup.",
      "evidence": [
        {
          "type": "official_menu",
          "label": "Tom Yum Noodle Soup",
          "source_url": "https://restaurant.example/order"
        }
      ]
    }
  ],
  "intent": {
    "summary": "Craving spicy soup",
    "constraints": [
      {
        "id": "c1",
        "dimension": "taste",
        "value": "spicy",
        "polarity": "include",
        "strength": "strong"
      },
      {
        "id": "c2",
        "dimension": "dish_type",
        "value": "soup",
        "polarity": "include",
        "strength": "preferred"
      }
    ]
  }
}
```

`high` confidence requires coherent structured official-menu support for all
important constraints. `medium` confidence may use visible official menu-page
text or query-specific provider evidence. If the pipeline times out, encounters
an outage, or cannot verify a sufficiently strong match, it returns an empty
recommendation list rather than a rating-based fallback.

## API routes

| Area | Routes | Access |
| --- | --- | --- |
| Chat | `GET /api/chat/status`, `POST /api/chat`, `POST /api/chat/stream` | Guest 18+ acknowledgment or accepted account policy; daily quota |
| Voice | `POST /api/audio/transcriptions` | Guest 18+ acknowledgment or accepted account policy; voice quota |
| Places | `GET /api/places/suggestions`, `POST /api/places/resolve`, `POST /api/places/dietary-evidence` | Guest or account Places quota |
| Legal | `GET /api/legal/current`, `POST /api/legal/accept` | Public read; verified account mutation |
| Registration/session | `POST /api/auth/register`, `/login`, `/logout` | Public/session |
| Email flows | `GET /api/auth/confirm`, `POST /api/auth/password/forgot`, `GET /api/auth/password/recovery`, `POST /api/auth/password/reset` | Public/transaction |
| Session data | `GET /api/auth/me`, `/csrf`, `/identities` | Session as applicable |
| Google identity | `GET /api/auth/google/start`, `/google/callback`, `POST /api/auth/identities/google/link`, `DELETE /api/auth/identities/google` | Public/session as applicable |
| Favorites | `GET`, `POST /api/favorites`; `/saved`; collection CRUD; notes; delete | Verified account |
| Preferences/consent | `GET`, `PATCH /api/account/preferences`; consent grant/withdraw; clear/reset controls | Verified account |
| Conversations | Cursor-paginated list, create/import/read/rename/delete/clear under `/api/conversations` | Verified account |
| Feedback | `POST /api/feedback` with a signed recommendation token | Verified account |
| Plans | `GET /api/plans`, `GET /api/account/entitlements` | Public plans; verified entitlements |
| Account | `GET /api/account/export`, `DELETE /api/account` | Verified account |

The old `/chat` and `/places/suggestions` paths remain temporary compatibility
aliases with the same security and quota controls.

## Configuration

All settings are documented in `.env.example`. The main groups are:

| Group | Variables |
| --- | --- |
| Providers | `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `VITE_GOOGLE_MAPS_API_KEY`, `MODEL_NAME` |
| Database | `DATABASE_URL`, `AUTO_CREATE_SCHEMA` |
| Supabase | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| Session security | `SESSION_ENCRYPTION_KEY`, `IDENTITY_SIGNING_SECRET`, session lifetime settings |
| Origins/proxy | `APP_ENV`, `FRONTEND_ORIGIN`, `PUBLIC_API_URL`, `ALLOWED_ORIGINS`, `TRUSTED_PROXY_IPS`, `VITE_DEV_API_TARGET` |
| Timeouts | `CHAT_PIPELINE_TIMEOUT_SECONDS`, `CHAT_RANKING_TIMEOUT_SECONDS` |
| Legal publication | `TERMS_VERSION`, `PRIVACY_VERSION`, `POLICY_EFFECTIVE_DATE`, `OPERATOR_LEGAL_NAME`, `OPERATOR_ADDRESS`, `GOVERNING_LAW`, `SUPPORT_EMAIL`, `PRIVACY_EMAIL` |
| Voice | `GUEST_DAILY_VOICE_SECONDS`, `ACCOUNT_DAILY_VOICE_SECONDS`, `AUDIO_MAX_BYTES` |
| Quotas | `DAILY_QUOTA_MULTIPLIER` plus guest, account, global, feedback, and authentication limit variables |
| Request limits | `REQUEST_BODY_LIMIT_BYTES` |

Generate a Fernet session encryption key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use at least 32 random characters for `IDENTITY_SIGNING_SECRET`.

## Authentication and data handling

Supabase access and refresh tokens never enter browser JavaScript. The backend
encrypts provider tokens at rest and gives the browser a random opaque
`HttpOnly` application-session cookie. State-changing account operations also
require a session-bound CSRF token and an allowed origin.

History is off by default. Temporary chat recovery uses tab-scoped
`sessionStorage`; it is cleared on tab close, New Chat, logout, or explicit
clearing. A verified user can separately opt into History or explicitly save
one conversation. Stored recommendation snapshots contain narrative and Place
IDs, never durable Google names, addresses, ratings, tags, photos, or photo
references.

The current prompt, bounded recent context, and confirmed map context are sent
to OpenAI for evidence-grounded recommendation processing; derived searches go
to Google Places, and selected public official restaurant sites may receive
bounded menu-evidence requests. Chat Completions explicitly set `store=false`.
OpenAI, Google, Supabase, Open-Meteo, and restaurant-site provider handling
applies independently of CraveAI's storage. Voice files are proxied to
`whisper-1` and held only in memory until transcription completes.

Production startup is intentionally blocked until the configured operator
identity, address, governing law, effective date, support email, and privacy
email replace the placeholders in `.env.example`. The legal documents are a
technical draft and require professional review before publication.

See [SECURITY.md](SECURITY.md) before changing authentication, authorization,
quota, logging, session, or data-handling boundaries. Production setup, key
rotation, retention, and incident procedures are in
[security operations](docs/security_operations.md). Google/Supabase callback
configuration is in [Google sign-in setup](docs/google_oauth_setup.md).

## Tests and evaluation

Run the complete local verification suite from the repository root:

```powershell
python -m pytest -q --basetemp=.test-tmp
python scripts\evaluate_recommendations.py --json
python scripts\benchmark_latency.py

cd frontend
npm test -- --run
npm run lint
npm run build
```

The recommendation evaluation contains 20 labeled synthetic cases. It compares
the production scorer against a deterministic proxy for the previous
information boundary:

| Metric | Previous proxy | Evidence-grounded scorer |
| --- | ---: | ---: |
| Precision@3 | 0.4333 | 0.6667 |
| Recall@3 | 0.6500 | 1.0000 |
| NDCG@3 | 0.4307 | 1.0000 |
| Constraint satisfaction | 0.4333 | 1.0000 |
| Unsupported-claim rate | 0.5667 | 0.0000 |
| Menu-evidence coverage | 0.0000 | 1.0000 |
| Strong matching-item rate | 0.4333 | 1.0000 |
| Mean results returned | 3.0000 | 2.0000 |

These metrics validate ranking and evidence gating under controlled labels.
They are not an estimate of live production quality and do not measure changing
Google coverage, official-site parsability, model variance, menu freshness,
distance preference, or user satisfaction. A live adjudicated evaluation is the
highest-priority measurement improvement.

The latest verified tree passes 60 backend tests and 54 frontend tests, plus
frontend lint, the production build, Python compilation, and the controlled
evaluation.

## Deployment and operations

The repository is arranged for this production boundary:

- Build `frontend/` on Vercel. `frontend/vercel.json` applies browser security
  headers, serves the SPA, and proxies `/api/*` to the Render backend.
- Run the backend on Python 3.11.9 with
  `uvicorn backend.main:create_app --factory`.
- Use Supabase transaction-pooler Postgres and run `alembic upgrade head` before
  deployment. Keep `AUTO_CREATE_SCHEMA=false` in production.
- Configure the external Vercel `/api` URL in Supabase email/OAuth redirects so
  authentication cookies remain first-party.
- Run `python scripts/security_maintenance.py` daily to enforce configured
  retention for abuse events, audit events, expired transactions, and revoked
  sessions.

CI in `.github/workflows/security.yml` runs tests, frontend checks, dependency
audits, migration rendering, and secret scanning.

## Current limitations

- Official menu coverage is uneven. JavaScript-only menus, PDFs, anti-bot pages,
  timeouts, and changed links may prevent verification.
- Google Places retrieval is query-sensitive and does not provide a general full
  menu field.
- On-demand evidence retrieval adds latency and currently examines only a
  bounded set of candidates and pages.
- Menu listings can be stale or temporarily unavailable. CraveAI is not an
  allergy-safety guarantee; users must confirm dietary and cross-contamination
  requirements with the restaurant.
- Distance is enforced through the search region but is not yet a calibrated
  component of the final score. Price and personalization are also limited.
- Official menu content and Google Places results are request-scoped rather than
  stored as a durable dish corpus.
- The current evaluation is controlled and small; it needs geographically
  representative human judgments and real product outcome signals.

## Documentation

- [Recommendation engine technical design](docs/technical_design.md)
- [Detailed recommendation overhaul](docs/recommendation_engine_overhaul.md)
- [Security policy](SECURITY.md)
- [Security operations](docs/security_operations.md)
- [Google sign-in setup](docs/google_oauth_setup.md)
- [Historical PRD](docs/PRD.md)—retained for planning history; its original
  LangChain/vector-store proposal is not the current implementation
