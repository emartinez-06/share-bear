# Local Development Environment

This document tells an agent (or a human) how to stand up and connect to the local dev server for `share-bear`, and what state it's currently in.

## Project shape

- Django 6.0.3 app. Entry point: `manage.py`.
- Apps: `core` (main app/views/models), `users` (custom `AUTH_USER_MODEL = 'users.User'`).
- Config: `config/settings.py`, `config/urls.py`.
- Deployed to Vercel (`vercel.json`, `@vercel/python`) on push to `main`.
- Database: Postgres via Supabase, configured through `DATABASE_URL`. Falls back to local SQLite (`db.sqlite3`) if `DATABASE_URL` is unset.

## One-time setup

```bash
cd /Users/eim/Projects/share-bear
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the project root (gitignored, never commit it). Required keys:

```env
DEBUG=True
SECRET_KEY=<any dev value>
ALLOWED_HOSTS=sharebear.app,www.sharebear.app,localhost,127.0.0.1
DATABASE_URL=<see "Database" section below>
```

## Starting the dev server

```bash
source venv/bin/activate
python3 manage.py runserver 127.0.0.1:8000
```

Verify it's up:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```

Server logs (when launched in background) are written to `/tmp/sharebear-runserver.log`.

**As of this writing, a dev server is already running in the background on port 8000, started for the user's active session. Don't kill/restart it casually — check `lsof -ti:8000` before assuming it's not running, and ask before restarting since it may be in active use.**

## Database: this project is wired to the real production Supabase Postgres

This is not a sandbox. `DATABASE_URL` in the local `.env` currently points at the **actual production** Supabase project (`sharebearWaitlist`, ref `wnslfnerrxywcblynxva`), the same database backing the live Vercel deployment. Any write from local (migrations, admin actions, form submits, `manage.py shell` writes) lands in real data.

**Default to read-only against this database.** Don't run `migrate`, `createsuperuser`, or anything that writes, without checking with the user first.

### Connection string shape

Supabase gives you three connection options; only one worked from this network:

| Option | Host pattern | Works here? |
|---|---|---|
| Direct connection | `db.<ref>.supabase.co` | No — IPv6-only, this network has no IPv6 route |
| Dedicated pooler | `db.<ref>.supabase.co` (different port) | No — same host, same IPv6-only problem |
| Transaction/Session pooler (Supavisor) | `aws-<N>-<region>.pooler.supabase.com` | **Yes** — has real A records (IPv4) |

The working format:

```
postgresql://postgres.wnslfnerrxywcblynxva:<password>@aws-0-us-west-2.pooler.supabase.com:6543/postgres
```

Notes:
- Username must be `postgres.<project-ref>` (not just `postgres`) when using the pooler.
- Port `6543` = transaction pooler mode, `5432` = session pooler mode. Either works; 6543 is what's currently in use.
- `sslmode=require` doesn't need to be in the URL — `config/settings.py`'s `build_default_database_config()` (around line 123) sets `options.setdefault('sslmode', 'require')` automatically regardless.
- In the Supabase "Connect" dialog, there's a free **"Use IPv4 connection"** toggle (switches to the shared pooler) — don't confuse it with the paid **"Enable IPv4 add-on"** button (dedicated IPv4 for the direct connection). Only the toggle was needed here.
- The actual password lives in `.env` only. If it ever needs to be reset again: Supabase dashboard → Connect → reset password → **also update the `DATABASE_URL` secret in Vercel and redeploy**, since the live site uses the same credential. Resetting one without the other breaks the live site.

### Local superuser note

A Django superuser (`admin` / dev password) was created early in this session, but that was against local SQLite, before `DATABASE_URL` was pointed at Supabase. It does not exist in the production database. No superuser currently exists in the real Supabase-backed `users_user` table — creating one there would be a write against production and should be confirmed with the user first.

## Supabase MCP access

A Supabase MCP server is registered at project scope (`.mcp.json`, committed — it only contains a project ref, no secrets):

```
claude mcp add --scope project --transport http supabase "https://mcp.supabase.com/mcp?project_ref=wnslfnerrxywcblynxva&features=docs,account,database,debugging,development,functions,branching"
```

This gives an agent direct tools (`list_tables`, `execute_sql`, `get_advisors`, `get_logs`, etc.) against the real Supabase project — separate from the Django app's own `DATABASE_URL` connection. Useful for inspecting schema/data or checking logs without going through the app.

Authentication is per-machine/session (OAuth). If tools like `mcp__supabase__list_tables` aren't available, the session needs to (re)authenticate — run `/mcp` in Claude Code, select `supabase`, and authenticate. Note: the `postgres` role itself cannot be altered via `execute_sql` (`ALTER USER postgres ...` fails with "Only superusers can alter privileged roles" — Supabase reserves that role's password changes for its own dashboard/management API).

## Known open issues (not fixed, flagged for follow-up)

1. **RLS is disabled on all 15 public tables** in the Supabase project (`django_migrations`, `auth_user`, `users_user`, `core_aiquote`, etc. — confirmed via `list_tables` advisory). Anyone with the project's public `anon` key can read/write every row if it's ever used client-side. Needs per-table policies designed before enabling; enabling RLS with no policies would lock the app out.
2. **Postgres log flood**: Supabase project logs show repeated `3F000 schema "pg_pgrst_no_exposed_schemas" does not exist` errors roughly every 30s. This is a Data API (PostgREST) misconfiguration, unrelated to this app's code (the app never queries through PostgREST — Django uses `psycopg` directly, video storage uses the Storage REST API). Fix: Supabase dashboard → Project Settings → Data API → Exposed schemas → ensure `public` is listed.
