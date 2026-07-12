# Site Traffic — To-do

1. [ ] Decide on Search Console API auth approach (service account vs OAuth) and where credentials are stored
2. [ ] Decide on Cloudflare API token scope (Analytics read) and where it's stored
3. [ ] Design the SQLite schema (site, date, search_hits, page_hits)
4. [ ] Write the daily pull script (cron, like backup.py) for the 3 initial sites (bowsy.co.uk, transformgov.org.uk, ukpolyamory.org)
5. [ ] Point daves-server-dashboard's Site Traffic section at the new DB instead of SITE_TRAFFIC_MOCK
6. [ ] Update the Site Traffic table to show display names (Bowsy, TransformGov, UK Polyamory) instead of full domains
7. [ ] Build the expanded stats page with graphs over time (replace the mock /site-traffic detail page)
8. [ ] Add remaining sites once the pipeline is proven (policycamp.org.uk, ukgovcomms.org, etc.)
