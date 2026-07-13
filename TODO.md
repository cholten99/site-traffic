# Site Traffic — To-do

1. [x] Decide on Search Console API auth approach (service account vs OAuth) and where credentials are stored
2. [x] Decide on Cloudflare API token scope (Analytics read) and where it's stored
3. [x] Design the SQLite schema (site, date, search_hits, page_hits)
4. [x] Write the daily pull script (cron, like backup.py) for the 3 initial sites (bowsy.co.uk, transformgov.org.uk, ukpolyamory.org)
5. [x] Point daves-server-dashboard's Site Traffic section at the new DB instead of SITE_TRAFFIC_MOCK
6. [x] Update the Site Traffic table to show display names (Bowsy, TransformGov, UK Polyamory) instead of full domains
7. [x] Build the expanded stats page with graphs over time (replace the mock /site-traffic detail page)
8. [~] Add remaining sites once the pipeline is proven — alobear.co.uk, aloysius-bear.co.uk, policycamp.org.uk added (Cloudflare/RUM live; Search Console pending the service account being added as a user on each); ukgovcomms.org and others still to come
