#!/usr/bin/env python3
"""Daily site-traffic pull: Search Console clicks/impressions + Cloudflare
requests/pageViews for each configured site, upserted into a local SQLite DB.

Re-pulls a trailing window each run (not just "yesterday") so a day's numbers
self-correct as Search Console's reporting lag catches up, rather than
needing separate backfill logic.
"""
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

import jwt

SECRETS_DIR = '/home/dave/secrets'
DB_PATH = '/var/www/site-traffic/site_traffic.db'
PULL_WINDOW_DAYS = 5

SITES = [
    # domain, display name, Cloudflare zone ID, Search Console property
    ('bowsy.co.uk',         'Bowsy',        '31ef5d67344395b08311a17f053cd5d4', 'sc-domain:bowsy.co.uk'),
    ('transformgov.org.uk', 'TransformGov', 'bb04c883d9dada64c9482f8e4224335b', 'sc-domain:transformgov.org.uk'),
    ('ukpolyamory.org',     'UK Polyamory', 'd300bf49cc010974ef0e988d87b1f128', 'sc-domain:ukpolyamory.org'),
]


def log(msg):
    print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}', flush=True)


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            search_clicks INTEGER,
            search_impressions INTEGER,
            page_views INTEGER,
            page_requests INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (site, date)
        )
    ''')
    con.commit()
    return con


def cf_token():
    with open(f'{SECRETS_DIR}/site_traffic_cf_token') as f:
        return f.read().strip()


def gsc_access_token():
    with open(f'{SECRETS_DIR}/site_traffic_google_sa.json') as f:
        sa = json.load(f)
    now = int(time.time())
    claims = {
        'iss': sa['client_email'],
        'scope': 'https://www.googleapis.com/auth/webmasters.readonly',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now,
        'exp': now + 3600,
    }
    assertion = jwt.encode(claims, sa['private_key'], algorithm='RS256')
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion,
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())['access_token']


def fetch_search_console(token, property_url, start, end):
    """Returns {date_str: (clicks, impressions)}."""
    url = ('https://www.googleapis.com/webmasters/v3/sites/'
           f'{urllib.parse.quote(property_url, safe="")}/searchAnalytics/query')
    body = json.dumps({
        'startDate': start.isoformat(),
        'endDate': end.isoformat(),
        'dimensions': ['date'],
    }).encode()
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    return {r['keys'][0]: (r['clicks'], r['impressions']) for r in payload.get('rows', [])}


def fetch_cloudflare(token, zone_id, start, end):
    """Returns {date_str: (requests, pageViews)}."""
    query = '''
    query {
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(limit: 20, filter: {date_geq: "%s", date_leq: "%s"}) {
            dimensions { date }
            sum { requests pageViews }
          }
        }
      }
    }
    ''' % (zone_id, start.isoformat(), end.isoformat())
    req = urllib.request.Request(
        'https://api.cloudflare.com/client/v4/graphql',
        data=json.dumps({'query': query}).encode(),
        method='POST',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    if payload.get('errors'):
        raise RuntimeError(payload['errors'])
    groups = payload['data']['viewer']['zones'][0]['httpRequests1dGroups']
    return {g['dimensions']['date']: (g['sum']['requests'], g['sum']['pageViews']) for g in groups}


def main():
    end = date.today() - timedelta(days=1)  # yesterday -- today's numbers are still incomplete
    start = end - timedelta(days=PULL_WINDOW_DAYS - 1)

    con = init_db()
    cf_tok = cf_token()
    gsc_tok = gsc_access_token()
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%S')

    for domain, display, zone_id, gsc_property in SITES:
        try:
            search_data = fetch_search_console(gsc_tok, gsc_property, start, end)
        except (urllib.error.URLError, KeyError) as e:
            log(f'ERROR: {domain} search console fetch failed: {e}')
            search_data = {}
        try:
            cf_data = fetch_cloudflare(cf_tok, zone_id, start, end)
        except (urllib.error.URLError, RuntimeError) as e:
            log(f'ERROR: {domain} cloudflare fetch failed: {e}')
            cf_data = {}

        d = start
        while d <= end:
            key = d.isoformat()
            clicks, impressions = search_data.get(key, (None, None))
            requests_, page_views = cf_data.get(key, (None, None))
            con.execute('''
                INSERT INTO daily_stats (site, date, search_clicks, search_impressions, page_views, page_requests, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site, date) DO UPDATE SET
                    search_clicks=excluded.search_clicks,
                    search_impressions=excluded.search_impressions,
                    page_views=excluded.page_views,
                    page_requests=excluded.page_requests,
                    fetched_at=excluded.fetched_at
            ''', (domain, key, clicks, impressions, page_views, requests_, now_iso))
            d += timedelta(days=1)
        con.commit()
        log(f'OK: {domain} updated {start} to {end}')

    con.close()


if __name__ == '__main__':
    main()
