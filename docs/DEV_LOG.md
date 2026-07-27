# Dev Session Log

Chronological record of infrastructure/setup work performed by an agent.
Not an auto-generated changelog — see git history for code-level changes.

## 2026-07-27 — Local dev environment stood up, then connected to production Supabase

**Initial local setup:**
- Created `venv/`, installed `requirements.txt`.
- Created `.env` with `DEBUG=True` and a dev `SECRET_KEY`. No `DATABASE_URL` set initially, so the app ran against local SQLite (`db.sqlite3`).
- Ran `python3 manage.py migrate` against SQLite.
- Started `runserver` on `127.0.0.1:8000`, verified with a `curl` (200 OK).
- Created a local Django superuser (`admin`) via `createsuperuser --noinput`, against the local SQLite database only.

**Diagnosed a Supabase Postgres log flood (unrelated to this app's code):**
- User reported Supabase logs flooding with `3F000 schema "pg_pgrst_no_exposed_schemas" does not exist`, repeating roughly every 30 seconds.
- Ruled out this repo/session as the cause (local server was on SQLite, no other Postgres-connecting process on the machine).
- Root cause: Supabase's Data API (PostgREST) schema-cache reload polling against an invalid "exposed schemas" config. Not fixed (dashboard-side setting); documented the fix location in `docs/ENVIRONMENT.md`.

**Connected local dev to the real production Supabase Postgres database:**
- Went through several iterations of `DATABASE_URL` before finding a working connection string:
  1. Direct connection host (`db.wnslfnerrxywcblynxva.supabase.co`) — failed. That host has no IPv4 (A record), only IPv6, and this network has no IPv6 route.
  2. "Dedicated pooler" (same host, different port) — failed for the same reason, same host.
  3. Shared pooler (Supavisor) via the dashboard's free **"Use IPv4 connection"** toggle — this produced a `aws-0-us-west-2.pooler.supabase.com` host with real IPv4 addresses. This worked.
- Along the way, also hit and resolved an authentication error (`Authentication credentials are invalid`) caused by a stale/incorrect password copied from the dashboard.
- Reset the production database password twice via the Supabase dashboard (direct `ALTER USER postgres` via SQL was attempted but rejected — Supabase reserves the `postgres` role's password changes for its own management API, not raw SQL).
- After the final reset, updated both the local `.env` and the `DATABASE_URL` secret in Vercel to the same new password, and the user redeployed/updated the live site — confirmed working on both sides.
- Verified the connection with a read-only query: `AIQuote.objects.count()` → 106, `User.objects.count()` → 43, matching the project's real data.

**Added Supabase MCP access for direct agent tooling:**
- Registered a project-scoped Supabase MCP server (`.mcp.json`) via `claude mcp add`, scoped to project ref `wnslfnerrxywcblynxva` with docs/account/database/debugging/development/functions/branching features.
- Completed OAuth authentication.
- Used it to inspect the schema (`list_tables`) and surfaced a critical, pre-existing finding: **Row Level Security is disabled on all 15 public tables**, meaning the project's public `anon` key can read/write every row if ever used client-side. Not fixed — flagged for the user to design per-table policies before enabling.

**End state:** local dev server running on `127.0.0.1:8000`, connected to the real production Supabase Postgres via the pooler, left running per the user's request. See `docs/ENVIRONMENT.md` for connection details and open issues.
