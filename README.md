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

## Scope (v1)

Starting with three sites:

- bowsy.co.uk — display name "Bowsy"
- transformgov.org.uk — display name "TransformGov"
- ukpolyamory.org — display name "UK Polyamory"

Other sites on the dashboard's existing mock list (policycamp.org.uk,
ukgovcomms.org, etc.) can be added once the pipeline is proven on these three.

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

## Open questions

- Where do the remaining credentials live? Likely the centralized
  `/home/dave/secrets/` store (`site_traffic_<name>`), matching the
  Cloudflare token and Google service account key above, rather than a new
  per-project `.env`.
- Retention: how long to keep daily history before rolling up or pruning?

## Status

Planning stage — no code written yet. Both Cloudflare and Search Console
access are proven and ready to use. See `TODO.md`.
