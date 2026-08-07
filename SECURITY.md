# Security Policy

## Supported code

Security fixes target the current `main` branch. Do not include credentials,
session cookies, OAuth codes, access tokens, personal data, or live exploit data
in a public issue.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for this repository. Include
the affected route or component, reproduction conditions, impact, and a minimal
proof of concept with secrets removed. If private reporting is unavailable,
contact the repository owner privately before publishing details.

## Security invariants

- Supabase access and refresh tokens are server-only and encrypted at rest.
- Browser authentication uses only a random opaque `HttpOnly` session cookie.
- State-changing account operations require a session-bound CSRF token and an
  allowed browser origin.
- Resource ownership comes from the authenticated session, never request data.
- Guest quota authority is server-derived; deleting browser storage cannot reset it.
- Passwords, tokens, cookies, OAuth codes, request bodies, and chat content are
  never written to application logs.
- Supabase service-role credentials are restricted to backend account deletion
  and must never be placed in frontend variables or source control.

## Data classification

| Class | Examples | Handling |
| --- | --- | --- |
| Restricted | Passwords, provider tokens, session/CSRF/recovery values | Never log or export; encrypt or hash at rest |
| Confidential | Email, favorites, feedback, IP-derived risk data, user audit events | Least-privilege access; delete on account deletion where applicable |
| Internal | Aggregate usage and security metrics | Backend/operations access only |
| Public | Restaurant source data | May be returned to guests |

Chat prompts and responses are processed ephemerally and are not persisted by
the application.

## Review scope

Security review includes authentication, authorization, OAuth/email recovery,
sessions, CSRF/CORS, quotas and automation controls, secrets, logging, database
migrations, account export/deletion, and provider error handling. Availability
and model recommendation quality are out of scope unless they cross one of
those security boundaries.
