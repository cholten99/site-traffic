# Site Traffic

Unified, historical view of search visibility (Google Search Console) and
audience (Cloudflare page hits) across a handful of sites, feeding a
dashboard section and — eventually — a stats page with graphs over time.

## Why

The "Site Traffic" section on [Dave's Server Dashboard](https://daves-server-dashboard.bowsy.co.uk)
currently shows static mock numbers (daily/weekly search hits and page hits
per site). This project replaces that mock with real numbers, pulled daily
and kept as history, so the section's linked detail page can plot trends
instead of a single day/week snapshot.

## Scope

Started with three sites, now six:

- bowsy.co.uk — display name "Bowsy"
- transformgov.org.uk — display name "TransformGov"
- ukpolyamory.org — display name "UK Polyamory"
- alobear.co.uk — display name "Alo Bear"
- aloysius-bear.co.uk — display name "Aloysius Bear"
- policycamp.org.uk — display name "PolicyCamp"

More can be added the same way (see "Site expansion" below). ukgovcomms.org
and others are still candidates.

## Planned architecture

- A daily cron job (same pattern as `backup.py` / `security-audit.sh` in
  `server-scripts`) pulls, per site:
  - **Search Console**: daily search hits via the Search Console API.
  - **Cloudflare**: daily page hits via the Cloudflare Analytics/GraphQL API.
- Results are written to a local SQLite database — one row per site per day —
  similar to how media-resize tracks `state.db`.
- `daves-server-dashboard`'s Site Traffic section reads the latest day plus
  trailing history from this DB instead of its current `SITE_TRAFFIC_MOCK` dict.
- A new expanded stats page (own small Flask app, reverse-proxied, following
  the media-resize pattern) shows historical graphs per site.

## Cloudflare access (resolved 2026-07-13)

- New token created in the CF dashboard, scoped to **Account > Account Analytics > Read**
  (not Zone > Analytics — that's a different, unrelated permission group; Account
  Analytics is what actually gates the GraphQL `httpRequests1dGroups` dataset
  used for page-hit counts, even for zone-scoped queries).
- Stored at `/home/dave/secrets/site_traffic_cf_token`, `dave:dave` `600`.
- Verified live against all three v1 zones via the GraphQL Analytics API
  (`https://api.cloudflare.com/client/v4/graphql`, `httpRequests1dGroups`,
  filtered by `zoneTag` + `date_geq`/`date_leq`). Confirmed working for:
  - bowsy.co.uk (zone `31ef5d67344395b08311a17f053cd5d4`)
  - transformgov.org.uk (zone `bb04c883d9dada64c9482f8e4224335b`)
  - ukpolyamory.org (zone `d300bf49cc010974ef0e988d87b1f128`)
- Note: `/user/tokens/verify` is the wrong endpoint to sanity-check this kind
  of token — it returned a misleading "Invalid API Token" for a token that
  was actually valid but under-permissioned. Use a real GraphQL query against
  the endpoint you actually need instead.

## Search Console access (resolved 2026-07-13)

- Used a dedicated **service account**, not OAuth — the 3 sites are verified
  under 3 different personal Google accounts, and a service account's identity
  is independent of any of them (adding it to a property works like sharing a
  Drive file with any email address). OAuth would have meant a separate
  client/token per owning account instead of one shared identity.
- New GCP project `site-traffic-502301`, Search Console API enabled, service
  account `site-traffic-reader@site-traffic-502301.iam.gserviceaccount.com`,
  no project-level IAM role needed (access comes entirely from being added as
  a user inside Search Console itself).
- JSON key stored at `/home/dave/secrets/site_traffic_google_sa.json`,
  `dave:dave` `600`.
- Added as a **Restricted** user on all three properties (each a
  domain-property, `sc-domain:<domain>`, under its own separate Google
  account) via Search Console → Settings → Users and permissions.
- Verified live: signed a JWT with the key, exchanged it for an access token
  (`scope=.../auth/webmasters.readonly`), and pulled real daily
  clicks/impressions from `searchAnalytics.query` for all three:
  - bowsy.co.uk
  - transformgov.org.uk
  - ukpolyamory.org
- Note: Search Console has **no public API for managing property users** —
  the "add user" step is UI-only and has to be repeated by hand (logged into
  whichever account owns it) for every future site added to this project.

## Pipeline (built 2026-07-13)

- `pull_daily.py` — pulls a trailing 5-day window (not just "yesterday") from
  both APIs and upserts into SQLite on every run. This is deliberate: Search
  Console's data has a 1-2 day reporting lag, so the most recent day or two
  come back `NULL` on first pull and get filled in automatically by a later
  run re-covering the same window, rather than needing separate backfill logic.
- Schema (`site_traffic.db`, `daily_stats` table): `site`, `date`,
  `search_clicks`, `search_impressions`, `page_views`, `page_requests`,
  `fetched_at`, primary key `(site, date)`. Stores both Search Console metrics
  and both Cloudflare metrics (not just the two the dashboard currently
  displays) so the future graphed stats page (#7) doesn't need a schema change.
- Scheduled via cron, `dave`'s crontab, daily at 06:30 UTC (after the 06:00
  security audit) — `/var/www/site-traffic/pull_daily.py >> logs/pull.log`.
- `daves-server-dashboard`'s Site Traffic section now reads live from this DB
  (`get_site_traffic()` / `get_site_traffic_detail()` in its `app.py`) instead
  of the old `SITE_TRAFFIC_MOCK` dict, and shows display names (Bowsy /
  TransformGov / UK Polyamory) instead of raw domains.
- "Daily" and "weekly" are computed independently per metric (not tied to one
  row) — if Search Console hasn't reported today's number yet but Cloudflare
  has, the table shows Cloudflare's fresh number rather than blanking both.

## Bot traffic (resolved 2026-07-13)

Raw Cloudflare `pageViews`/`requests` count every response regardless of who
asked for it, and turned out to be **~100-1000x** real human traffic on these
sites once compared against something bot-resistant — e.g. bowsy.co.uk showed
~943 raw pageViews/day vs. 3 RUM-confirmed human pageloads across an entire
week.

Fix: Cloudflare **Web Analytics** (RUM — a JS beacon that only fires in a real
browser) turned out to already be enabled account-wide, with a native `bot`
dimension on top of that for the JS-capable bots that do trigger it. Switched
to `viewer.accounts(...).rumPageloadEventsAdaptiveGroups`, filtered by each
site's RUM `siteTag` (a different ID from its Cloudflare zone ID — found via
the `requestHost` dimension on an unfiltered account-wide query). Schema keeps
both: `page_views`/`page_requests` (raw, for reference) and `page_human`/
`page_bot` (RUM, what the dashboard actually displays as "page hits").

One gotcha: unlike Search Console, RUM has no multi-day reporting lag, so a
date missing from the API response means zero events for that date, not
"data not arrived yet" — those get stored as `0`, not `NULL`.

## Site expansion (2026-07-13)

Added alobear.co.uk, aloysius-bear.co.uk, policycamp.org.uk. Cloudflare zone
IDs looked up via `GET /zones?name=<domain>`; RUM `siteTag`s found the same
way as the original three — an unfiltered account-wide
`rumPageloadEventsAdaptiveGroups` query, matched by the `requestHost`
dimension (Web Analytics was already enabled account-wide, same as before).

Search Console is **not yet granted** for these three — the service account
hasn't been added as a user on any of them yet, so `search_clicks`/
`search_impressions` come back `NULL` (403 from the API) until that manual
per-property step is done, same process as the original three. Cloudflare/RUM
data is live immediately since that's a single account-wide token, no
per-site grant needed.

Adding a new site from here is: 1) look up its CF zone ID and RUM siteTag,
2) add a row to `SITES` in `pull_daily.py` and to `SITE_TRAFFIC_SITES` in the
dashboard's `app.py`, 3) add the service account as a Restricted user on its
Search Console property.

## Open questions

- Retention: how long to keep daily history before rolling up or pruning?
  Not urgent yet — the DB is tiny at this scale.

## Status

Ingestion pipeline and graphed stats page (#7) both live. Six sites
configured; three still waiting on their Search Console grant (#8, see "Site
expansion" above). See `TODO.md`.
