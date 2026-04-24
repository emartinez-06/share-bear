# Supabase: remaining setup (SHARE Bear)

This app uses **Supabase PostgreSQL** for the Django `DATABASE_URL` and **Supabase Storage** for quote condition videos. Database hosting is already covered by your connection string. Below is what is still required on the **Storage** side (and in your environment) for video upload and admin playback to work.

## 1. Project URL and secrets (Django)

Add these to your deployment environment (e.g. `.env`). Do **not** commit the service role key to git.

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Project API URL, e.g. `https://<project-ref>.supabase.co` (Project Settings → API). |
| `SUPABASE_SERVICE_ROLE_KEY` | **Service role** secret (Project Settings → API). Used only on the **server** for uploads and signing URLs. Keep it private. |
| `SUPABASE_QUOTE_VIDEOS_BUCKET` | Optional. Defaults to `quote-videos` if unset. Must match the bucket name you create in the dashboard. |

**Why service role?** The Django app uploads files and creates signed “watch” links server-side. The anon key is not appropriate for that flow without extra RLS and client-side policies.

**Never** expose the service role key in the browser or in public repos.

## 2. Storage bucket

1. Open **Storage** in the Supabase dashboard.
2. **Create a new bucket** with name **`quote-videos`** (or set `SUPABASE_QUOTE_VIDEOS_BUCKET` to the same name).
3. Keep the bucket **private** (not public). The app serves videos to admins via **signed URLs** only.

## 3. Object paths the app uses

Uploads are stored with paths like:

`{user_id}/quote_{quote_id}/current.{ext}`

Example: `12/quote_45/current.mp4`

No manual folder setup is required; Storage creates the path on first upload. If you add lifecycle rules or cleanup jobs later, you can key off this pattern.

## 4. Storage policies and access

- The **Django app** uses the **service role** key, which in Supabase typically **bypasses** Row Level Security for Storage. If **uploads or signing fail** with 401/403 after the bucket exists, check the Supabase [Storage](https://supabase.com/docs/guides/storage) docs for your project version and ensure nothing blocks the service role (e.g. custom restrictions on the bucket).
- If you later add **client-side** (browser) uploads with the **anon** key, you will need **explicit storage policies** for `INSERT` / `SELECT` and possibly CORS. The current app does not require that for basic operation.

## 5. File size and duration

- The app enforces a max size via `QUOTE_VIDEO_MAX_BYTES` in Django (default 100 MB). Align this with your expectations.
- In Supabase, very large files may be subject to **project/plan** limits. Confirm **Storage** quota and any **per-object** or **body size** limits in your plan or dashboard.
- If you use a **CDN** or **Edge** in front of Storage later, add any extra config there; not required for the current server-side flow.

## 6. Manual verification checklist

- [ ] `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` set in the environment that runs Django.
- [ ] Bucket `quote-videos` (or your overridden name) exists and is private.
- [ ] From the app, sign in, complete a quote, and upload a small test video; confirm the row in Django has `has_video` and a non-empty `video_path`.
- [ ] In **Admin Quotes**, confirm **Watch** opens a playable signed URL (or fix signing until it does).
- [ ] **Accept offer** from the admin panel works end-to-end for that quote.

## 7. Optional / later

- **Backups and retention** for Storage objects (if you need compliance or cost control).
- **Virus scanning** or transcoding of uploads (not built into this app).
- **TUS / resumable uploads** in Supabase for very large files (current Django path reads the file into memory on upload; consider streaming or chunked upload if you increase limits significantly).

## Reference: Django settings

See `config/settings.py` for `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_QUOTE_VIDEOS_BUCKET`, and `QUOTE_VIDEO_MAX_BYTES`.
