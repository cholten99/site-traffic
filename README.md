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

## Open questions

- Search Console auth: which Google account/property verification is this
  tied to? Needs its own OAuth client_id/secret stored properly, not just a
  short-lived token (see the rclone OAuth lesson — tokens without a stored
  client_id/secret expire within days).
- Cloudflare auth: API token scope needed for Analytics/GraphQL per zone.
- Where do credentials live? Likely the centralized `/home/dave/secrets/`
  store rather than a new per-project `.env`.
- Retention: how long to keep daily history before rolling up or pruning?

## Status

Planning stage — no code written yet. See `TODO.md`.
