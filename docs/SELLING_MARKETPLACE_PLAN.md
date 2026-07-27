# Selling / Marketplace Rollout Plan

Status: draft, not yet started.
Tracks GitHub issue #7 ("purchasing lifecycle - listing -> checkout").
Companion to `docs/ENVIRONMENT.md` (how to run the app) and `docs/DEV_LOG.md` (session history).

## 1. Where we are today

SHARE Bear currently does one half of a circular-economy loop: buying items from students.
The flow is `AIQuote` end to end - submit item, get an AI price estimate, upload a condition video, admin approves, admin marks picked up.
Payment to the seller happens off-platform (cash/Venmo at pickup) and is tracked only as a status flag (`picked_up`, `quote_accepted_by_admin`) in the admin dashboard, not as a real transaction.

The nav already has a "Marketplace" link, but it currently points at the marketing landing page (`templates/index.html`), not a real catalogue.
There is no browsable inventory, no cart, no order, no payment model, and no Stripe anywhere in the codebase today (confirmed by grep across the repo).

This plan covers building the other half of the loop: reselling that inventory to Baylor students, with a real catalogue, cart, and checkout.

## 2. Assumptions

State these explicitly since they shape the data model - flag if any are wrong.

1. Inventory for sale is the same inventory already acquired through the buy-back pipeline (`AIQuote` rows with `picked_up=True`).
   This is a resale/circular model, not a separate supplier-sourced inventory stream.
2. The site stays Baylor-students-only end to end - buying reuses the same login gate as everything else (`AUTH_USER_MODEL = users.User`).
3. SHARE Bear is the sole seller of record for every listing (not a multi-vendor/peer-to-peer marketplace where students list their own items directly for sale to each other).

## 3. Decisions already made

**Fulfillment:** pickup by default (free), plus an optional delivery option for a fee, fulfilled by SHARE Bear staff driving items over - not a carrier/shipping-label integration.
This keeps fulfillment entirely in-house, matching how buy-back pickup already works.

**Payment sequencing:** ship the catalogue, cart, and checkout flow first with no live payment processing.
Phase 1 checkout ends in "pay at pickup/delivery," mirroring exactly how buy-back payouts work today (a manual, admin-marked "paid" flag, not a real transaction).
Stripe becomes a phase 2 addition once the core shopping flow is validated.

## 4. New data model

All new models live in `core/models.py` alongside `AIQuote`, using the same conventions (explicit `help_text`, `db_index` on status-like booleans, `Meta.ordering`).

- **`Listing`** - title, description, category, condition, `price` (real `DecimalField`, not the string-parsed `offer_display` pattern `AIQuote` uses - now that money changes hands for real, it needs to be an actual numeric currency field), `quantity`, `status` (draft/active/sold/archived), `source_quote` (nullable FK to `AIQuote`, for traceability back to the buy-back item it came from), `created_at`, `sold_at`.
- **`ListingImage`** - FK to `Listing`, object path in a new `listing-images` Supabase Storage bucket, `is_primary`, `sort_order`. Reuses the presigned-upload pattern already built for quote videos (`core/supabase_storage.py`, `quote_video_presigned_url_view`).
- **`Cart` / `CartItem`** - DB-backed and tied to `request.user` (not a session/anonymous cart - the whole site already requires login, so there's no cold-start case to design around).
- **`Order` / `OrderItem`** - created at checkout. `OrderItem` snapshots `price_at_purchase` (never trust a live join to `Listing.price`, since price can change after the order is placed). `Order` carries `fulfillment_method` (pickup/delivery), `delivery_address` + `delivery_fee` (delivery only), `payment_status` (unpaid/paid - manual in phase 1, Stripe-driven in phase 2), `fulfillment_status` (pending/ready/completed/cancelled), and (phase 2) `stripe_payment_intent_id`. Pickup scheduling reuses the same `google_event_id` / `pickup_starts_at` / `pickup_ends_at` fields pattern already proven on `AIQuote`.

## 5. Views and URLs

Public-facing:

- `/shop/` - catalogue grid: filter by category/price/condition, search. The filter-sidebar + grid/list pattern just built for the admin dashboard (`templates/admin_kanban.html`) is directly reusable here for the shopper-facing version.
- `/shop/<id>/` - listing detail: image gallery, price, condition, add-to-cart.
- `/cart/` - view/edit cart.
- `/checkout/` - phase 1: choose pickup vs delivery (+ address/fee if delivery), confirm order, no payment collected. Phase 2: redirect into a Stripe Checkout Session instead of the "confirm" step.
- `/orders/` - buyer-facing order history, parallel to the existing seller-facing `/accounts/items` ("My Items") page.

Admin-facing (same `is_staff`/`is_superuser` gate already used by `admin_kanban_view`):

- `/admin-dashboard/listings/` - create a listing directly from a picked-up `AIQuote` ("List this item for sale"), manage photos, set price/condition, publish/unpublish.
- `/admin-dashboard/orders/` - order fulfillment board. This can literally reuse the filter-sidebar + status-column + grid/list-toggle pattern just shipped for quotes: Pending -> Ready for pickup/Out for delivery -> Completed, plus a "mark paid" action for phase 1's manual payment tracking.

Marketing/nav:

- Point the existing "Marketplace" nav link at `/shop/` instead of `home`.
- Homepage (`templates/index.html`) is 100% buy-back copy today ("Sell your stuff") - needs a second CTA ("Shop the marketplace") added to the hero, not a full rewrite.
- Plan for a sparse-inventory cold-start state (a "check back soon" empty state) since catalogue depth depends entirely on buy-back throughput at launch.

## 6. Phased roadmap

### Phase 0 - Foundations
- `Listing` / `ListingImage` models + migration.
- `listing-images` Supabase bucket + upload flow (reuse `supabase_storage.py` + presigned URL pattern).
- Admin: create a listing from a picked-up quote, upload photos, set price/condition, publish/unpublish.
- Admin: listings management view (reuse the filter-sidebar/grid-list pattern).

### Phase 1 - Public catalogue, cart, manual-payment checkout
- `/shop/` catalogue with filters + search; listing detail page with image gallery.
- Cart (DB-backed, per user).
- Checkout: pickup vs delivery, delivery address + fee, order confirmation - no live payment, "pay at pickup/delivery."
- `Order` model + buyer-facing "My Orders" page.
- Admin order fulfillment board: mark paid, mark ready, mark completed.
- Nav/homepage updates: dual CTA, "Marketplace" link points at `/shop/`.

### Phase 2 - Stripe integration
- Stripe account + business verification (user-side task, not code).
- Test-mode keys wired via env vars, following the same pattern as `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`; Stripe CLI for local webhook testing.
- Stripe Checkout Session created at checkout time - redirect-based, so the app never touches raw card data.
- Webhook endpoint (`/stripe/webhook/`) to mark orders paid on `checkout.session.completed` and handle failure/expiry.
- Admin-triggered refund flow for cancelled orders.
- Switch checkout's default path from "pay at pickup" to "pay online"; keep manual/cash as an admin override for edge cases.

### Phase 3 - Explicitly deferred (listed so it isn't forgotten, not being built now)
- Reviews/ratings, wishlist/favorites.
- Search relevance/sorting improvements.
- Real transactional email (order confirmations, receipts). The site currently has **no automated email sending at all** - admin/approval "emails" are `mailto:` links the admin clicks manually. Phase 1 can reuse that same `mailto` pattern for order confirmations; automated email is new infrastructure (a Django email backend + a transactional provider) that would need its own scoping if wanted sooner.

## 7. Progress log

Updated as each increment lands; git history has the full detail, this is just the checklist view against section 6's roadmap.

### Phase 0 - Foundations
- [x] `Listing` / `ListingImage` models + migration (`core/migrations/0010_listing_listingimage.py`). Applied to production by Erick (`python3 manage.py migrate core 0010`) since Claude Code's own safety classifier blocks schema-changing Bash commands here. Verified via Supabase: `core_listing` and `core_listingimage` both exist, 0 rows.
- [x] Basic Django-admin registration (`/admin/`) for `Listing`/`ListingImage`, for visibility while the custom admin UI is pending.
- [x] `core/supabase_storage.py` generalized (bucket-parameterized internals) + `upload_listing_image` / `listing_image_public_url` added. Existing quote-video call sites untouched. Uses a server-side multipart upload (not presigned direct-to-client like video) since admin-uploaded listing photos are small and don't need to bypass Vercel's function payload path.
- [x] `listing-images` Supabase bucket created in production (public, unlike the private `quote-videos` bucket; 10 MB file size limit; JPEG/PNG/WebP only). Created via the Supabase MCP with Erick's go-ahead; `get_advisors` showed no new security findings afterward.
- [x] Admin: create a listing from a picked-up quote (`/admin-dashboard/listings/new/?from_quote=<id>`, prefills title/description/category/price), upload/delete photos, set price/condition/status. "List for sale" entry points added on the kanban board's Picked Up column and on the listings page's "not yet listed" section.
- [x] Admin: listings management view (`/admin-dashboard/listings/`) - simple status-tab table, not the full sidebar-filter treatment the buy-back board got (deliberately lighter weight for what will start as a handful of listings; can grow into the fuller pattern later if the catalogue gets large). All three admin pages (buy-back board, AI quotes, listings) now cross-link via a shared sub-nav.
- [x] Verified end-to-end against production: created a real listing, uploaded a photo, confirmed the public URL was fetchable, deleted the photo (confirmed both the DB row and the underlying Supabase Storage object were gone, via `storage.objects` and a cache-busted fetch), deleted the listing. Production `Listing` table is back to 0 rows.

### Phase 1 - Public catalogue, cart, manual-payment checkout
- [x] `/shop/` catalogue grid - search, category filter pills, "sold out" badge when quantity is 0, empty state for a bare catalogue. No login required to browse (confirmed with an anonymous test client) - login is only required starting at checkout, matching how the AI Quote page already works.
- [x] `/shop/<id>/` listing detail - image gallery (thumbnail strip swaps the main image), condition/category, description. No "Add to cart" yet since Cart doesn't exist - shows a "coming soon, contact us to arrange purchase" notice instead of a non-functional button.
- [x] "Marketplace" nav link across all 9 templates that had it now points to `/shop/` instead of the landing page.
- [x] Verified end-to-end against production (including as an anonymous/logged-out client) with a real listing + photo, then fully cleaned up.
- [x] Homepage hero rewritten to lead with buying: "Buy Dorm Essentials. Sold by Bears." with "Shop the marketplace" as the primary CTA and "Sell your stuff" as secondary (previously the only CTA, "Start a quote"). Fixed a small pre-existing bug where the desktop nav marked "Marketplace" as the active tab on the homepage even though home and shop are now different pages. Mobile bottom nav (in both `index.html` and `base_auth.html`, which duplicate this nav) swapped its second tab from "AI Quote" to "Shop", since mobile nav real estate is scarce and the ask was to make the marketplace prominent - AI Quote is still one tap away via desktop nav / the "Sell your stuff" hero button, just not in the 4 mobile bottom-bar slots anymore.
- [x] Bulk-created draft listings for all 52 currently picked-up, not-yet-listed buy-back items in production, via a new "List all N as drafts" action on the listings page (`admin_listings_bulk_create_view`). One item ("Coffee table") came through at $0 because its original AI quote never had a parseable offer amount - flagged for Erick to price manually before publishing. Everything else looks correct.
- [x] Photo upload now accepts multiple files in a single submission (was one file per request) - the admin listings table also got a small photo-count badge (red "!" when a listing has zero photos) so it's easy to track progress while working through a large batch of unlabeled images against many draft listings.
- [x] `Listing.msrp` / `Listing.msrp_url` added (migration `0011_listing_msrp_listing_msrp_url.py`, applied to production by Erick) plus a `percent_off` model property. Shop cards and the listing detail page now show a "% off" badge, a struck-through MSRP next to the current price, and a "See original retail listing" link when `msrp_url` is set. Editable from the admin listing form alongside price. Verified end-to-end on a real listing (MacBook Pro), then reverted back to its original state.
- [x] Click-to-enlarge image lightbox added on both the listing detail page (main image + thumbnails) and the admin edit page's photo gallery - useful while reviewing uploads, not just for shoppers.
- [x] Bulk-set `category='Furniture'` on all 36 listings that had no category, per Erick's explicit call after I flagged that a few of them (MacBook Pro, Headphones, fans, art, lamps) aren't actually furniture - he chose to apply it to all 36 anyway.
- [x] Image performance fix. Diagnosed the "slow to load / scrolling lags" complaint: 32 uploaded photos averaging 8.7 MB each (raw phone-camera resolution), 271 MB total, all downloaded at full size for what are mostly small thumbnails. Fixed in two parts:
  - `core/image_utils.py` (`resize_for_web`, using the new Pillow dependency) downscales to a 1920px max dimension and re-encodes at quality 85, respecting EXIF orientation. Wired into the upload view so every new photo goes through it automatically.
  - `python manage.py optimize_listing_images` (new management command, `--dry-run` supported) reprocesses everything already in storage. Ran it against production: 271 MB -> 8.6 MB, ~97% smaller per image, visual quality confirmed unaffected.
  - `loading="lazy"` + `decoding="async"` added to every below-the-fold image (shop grid, detail-page thumbnails, admin listings table, admin photo gallery) - the shop's above-the-fold main image stays eager since it's the primary content.
- [x] Pushed all Phase 0/1 work to `origin/main` (14 commits) - live via Vercel's auto-deploy on push to main.
- [x] Cross-referenced a folder of unattributed catalogue photos (`~/Downloads/Catalog Pics`, 11 photos) against listings missing photos. One matched an existing listing (photos attached to "Big tall white cabinets with black handles"). Three photos didn't match anything in the system at all - created new draft listings for them (floor lamp, standing desk, black bar stool) since they never went through the buy-back/AI-quote flow, so **all three are priced at $0.00 as a placeholder and need real pricing set before publishing**. The rest of the folder turned out to be duplicates of photos already uploaded elsewhere. Still genuinely missing photos: Grey and light brown chair, Grey horizontal accent pillow, Headphones, Loveseat/white couch, MacBook Pro, Owala 24oz.
- [ ] Cart (DB-backed, per user) - not started.
- [ ] Checkout (pickup vs delivery, manual "pay at pickup/delivery") - not started.
- [ ] `Order` model + buyer-facing "My Orders" page - not started.
- [ ] Admin order fulfillment board - not started.

### Phase 2 - Stripe integration
- [ ] Not started.

## 8. Open questions (need answers before or during build, not assumed)

- Is every sellable item sourced exclusively from the buy-back pipeline, or can admins add net-new inventory with no linked `AIQuote`?
- Delivery fee: flat rate, or distance/zone-based? Should the buyer's address be free text or a constrained campus-building picker, given delivery is Baylor-campus-only?
- Phase 1 "pay at pickup/delivery" - what payment methods does the admin actually need to record (cash, Venmo, Zelle, something else)?
- Sales tax: does Texas require tax collection on these sales, or is this treated as informal resale with none collected? This is a legal/compliance question, not a technical one - flagging so it isn't silently assumed away.
- Should the catalogue be browsable by logged-out visitors (gate only at checkout, for better marketing reach), or stay fully login-gated like the rest of the site today?
