# Issue #20: profile icon and usernames

## Behavior

The signed-in header now shows a 44-pixel profile icon linking to Account, with
an accessible name and tooltip identifying the username. The icon remains
available on mobile. The sidebar and account identity subtitle also use the
username, with "Food explorer" as the fallback for accounts without one.
Email remains available under the explicit Email address section in Account.
It no longer serves as the visible header/sidebar account identity.

New and existing accounts can choose or edit their username in Account.
Usernames contain 3–30 ASCII letters, digits, or underscores; the server trims
and lowercases them. A unique database index prevents duplicate names, including
concurrent claims. A rejected save preserves the entered value and supports
retry. Successful saves update the shared signed-in identity immediately and
persist across session refresh, sign-out, and subsequent login.

The new PATCH `/api/account/profile` endpoint uses the existing verified session,
allowed-origin, and CSRF protections. It selects the profile from the session's
user ID and rejects extra request fields. Usernames are presentation data and
do not affect authentication or account privileges. Login remains email-based.
Account exports include the username; existing profile deletion removes it.

The header sign-out confirmation now traps keyboard focus and returns focus to
its trigger after cancellation or Escape. Account links and username controls
retain native keyboard/touch interaction, labels, and announced save/error states.

## Database rollout

Apply migration `0003_profile_username` with `alembic upgrade head` **before
deploying the updated backend**, then deliver the frontend. It adds a nullable
username column and a unique index, preserving existing profiles without
deriving any username from email. The current production database must already
have the existing migrations applied.

`AUTO_CREATE_SCHEMA=true` creates new tables for fresh local/test databases;
it does not add columns to an existing SQLite database. For an existing local
SQLite database created without Alembic tracking, apply the following additive
SQL once (after checking that the column/index are absent):

```sql
ALTER TABLE profiles ADD COLUMN username VARCHAR(30);
CREATE UNIQUE INDEX uq_profiles_username ON profiles (username);
```

No hosted database was modified during this implementation.

## Verification

- Full backend suite: 116 tests passed. New coverage checks persistence, export,
  normalization, duplicate rejection, account isolation, invalid inputs, missing
  sessions/CSRF, rejected origins, and migration preservation/rollback.
- Full frontend suite: 87 tests passed. New coverage checks profile icon labels,
  fallback identity, sidebar identity, successful/rejected saves, shared auth
  updates, and sign-out focus trapping/restoration.
- Frontend lint, production build, and `git diff --check` passed.
- Browser checks passed for 18 combinations: 1440/390/320-pixel widths, light/dark
  theme classes, and legacy/named/maximum-length usernames. They exercise
  keyboard or touch account navigation, mobile drawer identity, 44-pixel icon
  targets, duplicate-name recovery, successful saves, reload persistence,
  header identity after return, and sign-out cancellation/completion. No browser
  page errors or page-level horizontal overflow were observed.
- Browser APIs were mocked. Backend tests exercise the actual app endpoints and
  local database with a fake identity provider; live Supabase and deployment
  behavior were not exercised. Authentication pages retain their existing light
  design; the profile icon uses the shared theme colors.
- Migration upgrade/downgrade was exercised against an existing SQLite profile;
  PostgreSQL migration SQL rendered successfully without connecting to a hosted
  database.
- TypeScript still reports seven existing errors in chat/client APIs, App tests,
  ProductPages, and SuggestionCard. Two pre-existing missing test imports were
  fixed in the account/sidebar test files touched here. No new TypeScript errors
  were introduced.

Implemented and verified locally on 2026-09-30. Deployment has not been verified;
the database rollout above is required before deploying the updated backend.
