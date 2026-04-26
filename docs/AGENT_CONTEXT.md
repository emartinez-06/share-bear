# SHARE Bear — Agent Context Document

> For any AI agent picking up work on this repo. Read this before touching anything.

---

## What This Project Is

SHARE Bear is a Django web app for a student buy-back marketplace at Baylor University, built in collaboration with 180 Degrees Consulting BU and Baylor UIF. Students submit items they want to sell via an AI-powered quote form, upload a condition video, and book a pickup time. Admin staff review submissions and manage the pickup lifecycle.

**Live stack:** Django 6.x · Tailwind CSS (CDN, no build step) · Google Material Symbols (CDN) · Supabase Storage (video files) · Google Gemini API (quote generation) · Vercel (deployment)

---

## Codebase Map

```
share-bear/
├── config/
│   ├── settings.py          # All env-driven config (SUPABASE_*, GEMINI_*, etc.)
│   └── urls.py              # All URL patterns
├── core/
│   ├── models.py            # AIQuote model (single model, all fields)
│   ├── views.py             # All views — user-facing + admin
│   ├── forms.py             # AIQuoteForm, QuoteVideoForm, BookingLinkForm
│   ├── gemini_quote.py      # Gemini API integration + prompt builder
│   ├── supabase_storage.py  # Supabase Storage REST client (upload + signed URLs)
│   └── video_utils.py       # File extension helper for uploads
├── users/
│   ├── models.py            # Custom User model (extends AbstractUser)
│   ├── views.py             # signup, login, profile
│   └── urls.py              # /accounts/* routes
├── templates/
│   ├── base_auth.html       # Base template (Tailwind, fonts, analytics)
│   ├── index.html           # Marketplace home
│   ├── ai_quote.html        # Quote submission form
│   ├── ai_quote_success.html # Quote result + video upload + booking link
│   ├── admin_kanban.html    # Admin Kanban board (3 columns + modals)
│   ├── admin_quotes.html    # Legacy flat-table admin view (still accessible)
│   └── users/
│       ├── login.html
│       ├── signup.html
│       └── profile.html     # User's past quotes
├── static/
│   └── images/bearLogo.png
└── docs/
    ├── SUPABASE_REMAINING.md
    └── AGENT_CONTEXT.md     # this file
```

---

## Auth Model

- **Custom User** extends `AbstractUser` — lives in `users/models.py`
- **Two user roles** (no separate model, just flags on the same User):
  - **Seller** — any authenticated user; can submit quotes, upload videos, save booking links
  - **Admin** — `user.is_staff = True` OR `user.is_superuser = True`; can access the Kanban dashboard and approve/pickup items
- `LOGIN_URL` is `/accounts/login/` (configured in `settings.py`)
- Admin pages guard with `if not (request.user.is_staff or request.user.is_superuser): return HttpResponseForbidden(...)`

---

## AIQuote Model — Full Field List

```python
class AIQuote(models.Model):
    user                          # ForeignKey -> AUTH_USER_MODEL
    item_name                     # CharField(200)
    description                   # TextField
    make                          # CharField(120, blank=True)
    model                         # CharField(120, blank=True)
    unknown_make_model            # BooleanField
    quote_text                    # TextField — raw Gemini response
    has_video                     # BooleanField — True after video uploaded
    video_path                    # CharField — object path in Supabase bucket
    quote_accepted_by_admin       # BooleanField — Awaiting -> Approved transition
    quote_reviewed_at             # DateTimeField(null=True) — set on approval
    booking_link                  # URLField(1024, blank=True) — Microsoft Booking URL
    picked_up                     # BooleanField — Approved -> Picked Up transition
    picked_up_at                  # DateTimeField(null=True) — set on pickup
    admin_confirmed_offer_display # CharField(32, blank=True) — admin override price
    created_at                    # DateTimeField(auto_now_add=True)

    @property offer_display   # Returns admin_confirmed_offer_display if set,
                              # otherwise parses quote_text via format_share_bear_offer_display()
```

**Kanban column mapping:**

| Column | Filter |
|--------|--------|
| Awaiting | `quote_accepted_by_admin=False` |
| Approved | `quote_accepted_by_admin=True AND picked_up=False` |
| Picked Up | `picked_up=True` |

---

## URL Structure

| URL | View | Name |
|-----|------|------|
| `/` | `home_view` | `home` |
| `/ai-quote/` | `ai_quote_view` | `ai_quote` |
| `/ai-quote/dev-success/` | `ai_quote_dev_success_view` | `ai_quote_dev_success` |
| `/ai-quote/complete/<id>/` | `ai_quote_success_detail_view` | `ai_quote_success_detail` |
| `/ai-quote/complete/<id>/video/` | `quote_video_upload_view` | `quote_video_upload` |
| `/admin-dashboard/` | `admin_kanban_view` | `admin_kanban` |
| `/admin-dashboard/approve/<id>/` | `admin_kanban_approve_view` | `admin_kanban_approve` |
| `/admin-dashboard/pickup/<id>/` | `admin_kanban_pickup_view` | `admin_kanban_pickup` |
| `/admin-dashboard/unapprove/<id>/` | `admin_kanban_unapprove_view` | `admin_kanban_unapprove` |
| `/admin-dashboard/unpickup/<id>/` | `admin_kanban_unpickup_view` | `admin_kanban_unpickup` |
| `/admin-quotes/` | `admin_quotes_view` | `admin_quotes` (legacy) |
| `/admin-quotes/accept/<id>/` | `admin_accept_quote_view` | `admin_accept_quote` (legacy) |
| `/accounts/login/` | login | `login` |
| `/accounts/signup/` | signup | `signup` |
| `/accounts/logout/` | logout | `logout` |
| `/accounts/profile/` | profile | `profile` |

---

## Features Built

### AI Quote Form (`/ai-quote/`)
- User fills item name, description, make/model (or checks "unknown make/model")
- `build_quote_prompt()` + `get_quote_from_gemini()` in `core/gemini_quote.py` call Google Gemini
- Authenticated users: quote saved to DB, redirected to `/ai-quote/complete/<id>/?celebrate=1`
- Unauthenticated users: result rendered inline, not saved
- `DEV_MOCK_QUOTE_ITEM_NAME` / `DEV_MOCK_OFFER_DISPLAY` constants bypass Gemini in DEBUG mode

### Quote Success Page (`/ai-quote/complete/<id>/`)
- Shows item name, offer amount, video upload section, Microsoft Booking link form
- **Video upload:** POST to `/ai-quote/complete/<id>/video/` → `quote_video_upload_view` → Supabase Storage; sets `has_video=True`, `video_path="{user_pk}/quote_{quote_pk}/current{ext}"`
- **Booking link:** POST to same detail URL → `BookingLinkForm` saves `booking_link` field via `update_fields=['booking_link']`
- `show_confetti` context flag triggers JS confetti on `?celebrate=1`

### Admin Kanban Dashboard (`/admin-dashboard/`)
- Staff-only; 403 for non-staff authenticated users, redirect to login for unauthenticated
- Three-column board rendered server-side: Awaiting / Approved / Picked Up
- Cards are `<button>` elements; clicking opens a hidden modal via `openModal('modal-{pk}')`
- Modals contain: user info, dates, make/model, description, offer, inline video player, booking link, action buttons
- Signed URLs generated at page-load with `expires_in=1200` (20 min) and attached as `q.signed_video_url` dynamic attribute in the view
- `closeModal()` calls `el.querySelectorAll('video').forEach(v => v.pause())` to stop playback on close
- Escape key closes any open modal

### Kanban Status Transitions

| Action | View | DB change |
|--------|------|-----------|
| Approve | `admin_kanban_approve_view` | `quote_accepted_by_admin=True`, `quote_reviewed_at=now()` |
| Mark Picked Up | `admin_kanban_pickup_view` | `picked_up=True`, `picked_up_at=now()` |
| Revert to Awaiting | `admin_kanban_unapprove_view` | `quote_accepted_by_admin=False`, `quote_reviewed_at=None` |
| Revert to Approved | `admin_kanban_unpickup_view` | `picked_up=False`, `picked_up_at=None` |

**Guards enforced in views:**
- Approve blocked if `has_video=False` → error message
- Approve blocked if already approved → info message
- Unapprove blocked if item is in Picked Up state → error (must unpickup first)
- Pickup blocked if not yet approved → error
- All transitions idempotent with appropriate messages

### User Profile Page (`/accounts/profile/`)
- Shows account info (name, username, graduation year, member since)
- Lists all past AI quotes with offer amount, video/review status badges, link to detail page

---

## Bug Fixes Applied This Session

### Supabase Signed URL 404 (`core/supabase_storage.py:create_signed_video_url`)

**Symptom:** Videos uploaded successfully (downloadable from Supabase dashboard directly) but signed URLs returned HTTP 404 when the browser tried to load them.

**Root cause:** Supabase's sign API (`POST /storage/v1/object/sign/{bucket}/{path}`) returns `signedURL` as a relative path starting with `/object/sign/...` — without the `/storage/v1` prefix. The original code path was:

```python
if signed.startswith('/'):
    return f'{base}{signed}'
# produced: https://project.supabase.co/object/sign/...  <- 404
```

The correct URL must be:
```
https://project.supabase.co/storage/v1/object/sign/...
```

**Fix applied:**
```python
if signed.startswith('/storage/v1'):
    return f'{base}{signed}'
if signed.startswith('/'):
    return f'{base}/storage/v1{signed}'  # insert missing prefix
return f'{base}/storage/v1/{signed}'
```

---

## Supabase Storage Configuration

- **Bucket name:** `quote-videos` (env `SUPABASE_QUOTE_VIDEOS_BUCKET`, default `"quote-videos"`)
- **Bucket type:** Private
- **Auth:** Service Role Key (`SUPABASE_SERVICE_ROLE_KEY`) for both upload and signed URL generation — never the anon key
- **Object path format:** `{user_pk}/quote_{quote_pk}/current{ext}` — e.g. `2/quote_3/current.mp4`
- **Upload mode:** upsert (`x-upsert: true`) so re-uploads overwrite the same path
- **Max video size:** `QUOTE_VIDEO_MAX_BYTES` in settings (default 100 MB)

---

## CSS / Design System

- **No build step** — Tailwind CSS loaded from CDN in `base_auth.html`
- **Color tokens:**
  - `primary` = `#003020` (dark forest green)
  - `secondary-container` = `#feb71a` (amber/gold)
  - `surface`, `surface-container`, `surface-container-lowest`, `on-surface`, `on-surface-variant`, `outline-variant` — Material You surface tokens
- **Typography:** `font-display` (headings) · `font-body` (body) · `tracking-tightest`
- **Icons:** Google Material Symbols Outlined — `<span class="material-symbols-outlined">icon_name</span>`
- **Animation:** `fade-up` utility class defined in `base_auth.html`

---

## Patterns to Follow

1. **No separate JS files** — all JS is inline `<script>` at the bottom of each template's `{% block body %}`
2. **No AJAX** — all interactions are standard HTML form POST + redirect (PRG pattern)
3. **Admin auth guard order:** check `is_authenticated` first (redirect to login), then check `is_staff or is_superuser` (403 forbidden)
4. **Always use `update_fields`** — `save(update_fields=['field1', 'field2'])` on every model save, never bare `.save()`
5. **Django messages framework** for all user feedback — `messages.success/error/info`; templates render the message list at the top of `<main>`
6. **Signed URLs are ephemeral** — generated fresh on each admin dashboard page load, never stored in DB
7. **Inline video player** — use `<video controls playsinline preload="metadata"><source src="..."></video>` instead of `<a href="...">` links to avoid browser Content-Disposition download behavior from Supabase private bucket URLs

---

## Environment Variables (all required in production)

```
SECRET_KEY=
DEBUG=False
SUPABASE_URL=https://wnslfnerrxywcblynxva.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_QUOTE_VIDEOS_BUCKET=quote-videos
GEMINI_API_KEY=
VERCEL_ANALYTICS_ENABLED=True
LOGIN_URL=/accounts/login/
QUOTE_VIDEO_MAX_BYTES=104857600
```

---

## Known Remaining Work

- No email/notification to user when admin approves or marks pickup
- No pagination on admin dashboard (loads all quotes; legacy view caps at 200)
- Legacy `/admin-quotes/` flat-table view still exists alongside the Kanban board — may be retired
- `AdminAcceptQuoteForm` in the legacy view has a `final_offer` field for overriding the AI price; Kanban board uses the AI price directly without override
- Microsoft Booking link is free-text URL from user with no validation against a real booking system
- Supabase MCP (`mcp__claude_ai_Supabase__*`) requires a project-scoped auth token; add it via:
  ```
  claude mcp add --scope project --transport http supabase \
    "https://mcp.supabase.com/mcp?project_ref=wnslfnerrxywcblynxva"
  ```
