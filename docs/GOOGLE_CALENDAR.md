# Google Calendar pickup (SHARE Bear)

## What it does

- **Presets in the app:** Bookable times come from a weekly configuration (`PICKUP_WEEKLY_SLOT_DEFINITIONS`, loaded from `PICKUP_WEEKLY_SLOTS_JSON` or a built-in default). The organization calendar does **not** need placeholder events; availability is the preset grid minus any slot already taken in the app database.
- **Google:** When a user books, the app calls **`events.insert`** on the first calendar in `GOOGLE_SLOT_SOURCE_CALENDAR_IDS` and stores `google_calendar_id`, `google_event_id`, the HTML link, and `pickup_starts_at` / `pickup_ends_at` on each selected `AIQuote`. Taken slots no longer appear in the picker (same time must not be assigned to an existing completed booking row).

## Environment variables

| Variable | Required | Notes |
|----------|----------|--------|
| `GOOGLE_SERVICE_ACCOUNT_KEY_JSON` | Yes* | Preferred for Vercel/serverless. Full service account JSON content as one env var value. Do not commit. |
| `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` | Yes* | Path to a **service account JSON** key file. Use when a local/server file is available. Do not commit. |
| `GOOGLE_SLOT_SOURCE_CALENDAR_IDS` | Yes | Comma-separated calendar **IDs** where new pickup **events are created** (first ID is used for `insert`), e.g. `sharebearhelp@gmail.com`. The embed URL `...?src=...` encodes the same address. |
| `GOOGLE_PICKUP_SLOT_DAYS_AHEAD` | No | Default `30`. How far out to list preset instances. |
| `GOOGLE_PICKUP_TIMEZONE` | No | Default `America/Chicago`. Used to interpret weekly `HH:MM` windows. |
| `PICKUP_WEEKLY_SLOTS_JSON` | No | JSON array of slot rows. **weekday** uses Python’s `date.weekday()`: **Monday=0 … Sunday=6**. **Single slot:** `{"weekday": 4, "start": "14:00", "end": "14:30"}`. **Hourly (1-hour blocks):** `{"weekday": 4, "hourly": true, "first": "09:00", "last_start": "17:00"}` — slots 9:00–10:00 through 17:00–18:00. If missing or invalid, the default is **Fri & Sat** 9:00–18:00 hourly and **Sun** 12:00–18:00 hourly in `GOOGLE_PICKUP_TIMEZONE`. |
| `PICKUP_EVENT_TITLE` | No | Default `SHARE Bear — Item pickup` — the Google event **summary** on insert. |

## Google Cloud and Calendar setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com), enable **Google Calendar API**, create a **Service account**, download a **JSON** key.
2. In [Google Calendar](https://calendar.google.com), for the **destination** calendar, **Settings → Share with people** → add the service account’s **email** (ends with `gserviceaccount.com`) with **Make changes to events** (or equivalent).
3. You do not need to pre-create empty “slot” events; the app inserts each booking as a new event. Optional: add that calendar to a website embed for visibility.
4. Set env vars on the host; restart the app.

\* Configure **either** `GOOGLE_SERVICE_ACCOUNT_KEY_JSON` **or** `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`.

## Slot visibility

- A preset instance is **hidden** if any `AIQuote` already has that **exact** `pickup_starts_at` and a non-empty `google_event_id` (a completed booking in the app).

## Key rotation

If a service account or API key is exposed, create a new key, update `GOOGLE_SERVICE_ACCOUNT_KEY_JSON` or `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`, and revoke the old key in Google Cloud.
