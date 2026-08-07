# Security Operations

## Production setup

1. Run `alembic upgrade head` against the Supabase Postgres database.
2. Configure the frontend URL as `FRONTEND_ORIGIN` and its externally visible
   `/api` URL as `PUBLIC_API_URL`.
3. Add `${PUBLIC_API_URL}/auth/confirm`,
   `${PUBLIC_API_URL}/auth/password/recovery`, and
   `${PUBLIC_API_URL}/auth/google/callback` to the Supabase redirect allowlist.
4. Enable email confirmation, set the minimum password length to 12, and
   configure Resend SMTP in the Supabase Auth SMTP settings using a verified
   sender domain.
   Configure server-readable email links in the Supabase templates:

   - Confirmation:
     `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=signup`
   - Recovery:
     `{{ .RedirectTo }}?token_hash={{ .TokenHash }}`

   Do not place access or refresh tokens in frontend redirect fragments.
5. Configure Google in Supabase Auth and the Google Cloud console. Use the
   Supabase provider callback displayed in the dashboard. Enable Supabase's
   **Manual Linking** option. CraveAI records approved identity methods and
   rejects/undoes an unexpected automatic same-email link, requiring the user
   to sign in with the existing method before connecting Google.
6. Store `DATABASE_URL`, Supabase keys, `SESSION_ENCRYPTION_KEY`,
   `IDENTITY_SIGNING_SECRET`, and provider keys in Render/Vercel secret stores.
7. Set `TRUSTED_PROXY_IPS` only to verified immediate proxy addresses. Forwarded
   client-IP headers are ignored from every other peer.
8. Keep `AUTO_CREATE_SCHEMA=false` in production.

Before cutover, confirm the legacy SQLite tables are still empty. If any row
exists, stop rather than silently losing or misattributing data:

```powershell
python scripts/check_legacy_sqlite_empty.py data/craveai.db
```

The command opens SQLite read-only and exits with a nonzero status when any
application table contains rows.

## Key rotation

- Rotate the Supabase anon key by updating the backend secret; it is not used by
  the browser in this architecture.
- Rotate the service-role key immediately after suspected disclosure.
- Rotating `SESSION_ENCRYPTION_KEY` invalidates existing encrypted provider
  sessions unless a dual-key decrypt window is implemented. Schedule a
  maintenance window and revoke all app sessions.
- Rotating `IDENTITY_SIGNING_SECRET` invalidates guest continuity and changes
  server-derived risk hashes. Keep the old value only for the minimum required
  overlap.
- After any authentication-secret rotation, test login, refresh, logout, Google
  OAuth, recovery, and account deletion.

## Account compromise

1. Revoke all app sessions for the user.
2. Review sanitized authentication audit events and Supabase Auth logs.
3. Require password recovery and review linked identities.
4. Rotate provider credentials if compromise may be systemic.
5. Preserve only necessary audit evidence; never copy tokens or chat content
   into an incident ticket.

## Provider outage

Authentication provider failures return a generic `503` and must not fall back
to unsigned identities. Existing application sessions may continue until their
configured expiry, but identity-management and deletion operations fail closed.
OpenAI or Places outages must not bypass the already-reserved quota.

## Retention

Run `python scripts/security_maintenance.py` daily. It deletes abuse events after
30 days, security audit events after 90 days, expired auth transactions, and
revoked application sessions after 30 days. Favorites and feedback remain until
account deletion. Chat content is not stored.
