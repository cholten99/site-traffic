#!/usr/bin/env python3
"""Daily site-traffic pull: Search Console clicks/impressions, raw Cloudflare
requests/pageViews, and Cloudflare Web Analytics (RUM) human/bot pageloads
for each configured site, upserted into a local SQLite DB.

Re-pulls a trailing window each run (not just "yesterday") so a day's numbers
self-correct as Search Console's reporting lag catches up, rather than
needing separate backfill logic.

Raw Cloudflare pageViews/requests count every response regardless of who
asked for it (crawlers, scrapers, monitoring), which turned out to be
~100-1000x the real human traffic on these sites (verified 2026-07-13). RUM
data (page_human/page_bot) comes from Cloudflare's Web Analytics beacon,
which only fires in a real browser, and is what the dashboard actually
displays as "page hits" -- the raw CF numbers are kept for reference only.
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
CF_ACCOUNT_ID = '2eb5ec3a089fa8e5e15fa523bd999cf3'

SITES = [
    # domain, display name, Cloudflare zone ID, Search Console property, RUM siteTag
    ('bowsy.co.uk',         'Bowsy',        '31ef5d67344395b08311a17f053cd5d4', 'sc-domain:bowsy.co.uk',         '4c4becd7ddee4238b282612265dbef0b'),
    ('transformgov.org.uk', 'TransformGov', 'bb04c883d9dada64c9482f8e4224335b', 'sc-domain:transformgov.org.uk', 'c0a3b3e2ead4449fb4fc006565f73958'),
    ('ukpolyamory.org',     'UK Polyamory', 'd300bf49cc010974ef0e988d87b1f128', 'sc-domain:ukpolyamory.org',     'c84a4c9d5c5a45b487c9fe480cb2770a'),
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
            page_human INTEGER,
            page_bot INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (site, date)
        )
    ''')
    # Added after the table already existed in production -- ALTER TABLE has
    # no "IF NOT EXISTS" for columns, so just swallow the duplicate-column
    # error on runs where they're already there.
    for col in ('page_human', 'page_bot'):
        try:
            con.execute(f'ALTER TABLE daily_stats ADD COLUMN {col} INTEGER')
        except sqlite3.OperationalError:
            pass
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


def fetch_rum(token, site_tag, start, end):
    """Returns {date_str: (human_pageloads, bot_pageloads)} from Cloudflare
    Web Analytics (RUM) -- only fires from a real browser executing the
    beacon JS, with Cloudflare's own bot classification on top of that."""
    query = '''
    query {
      viewer {
        accounts(filter: {accountTag: "%s"}) {
          rumPageloadEventsAdaptiveGroups(limit: 100, filter: {siteTag: "%s", date_geq: "%s", date_leq: "%s"}) {
            count
            dimensions { date bot }
          }
        }
      }
    }
    ''' % (CF_ACCOUNT_ID, site_tag, start.isoformat(), end.isoformat())
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
    groups = payload['data']['viewer']['accounts'][0]['rumPageloadEventsAdaptiveGroups']
    result = {}
    for g in groups:
        d = g['dimensions']['date']
        human, bot = result.get(d, (0, 0))
        if g['dimensions']['bot']:
            bot += g['count']
        else:
            human += g['count']
        result[d] = (human, bot)
    return result


def main():
    end = date.today() - timedelta(days=1)  # yesterday -- today's numbers are still incomplete
    start = end - timedelta(days=PULL_WINDOW_DAYS - 1)

    con = init_db()
    cf_tok = cf_token()
    gsc_tok = gsc_access_token()
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%S')

    for domain, display, zone_id, gsc_property, rum_site_tag in SITES:
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
        try:
            rum_data = fetch_rum(cf_tok, rum_site_tag, start, end)
        except (urllib.error.URLError, RuntimeError) as e:
            log(f'ERROR: {domain} RUM fetch failed: {e}')
            rum_data = {}

        d = start
        while d <= end:
            key = d.isoformat()
            clicks, impressions = search_data.get(key, (None, None))
            requests_, page_views = cf_data.get(key, (None, None))
            # Unlike Search Console, RUM has no multi-day reporting lag -- a
            # date missing from the response means zero events, not unknown.
            page_human, page_bot = rum_data.get(key, (0, 0))
            con.execute('''
                INSERT INTO daily_stats (site, date, search_clicks, search_impressions, page_views, page_requests, page_human, page_bot, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site, date) DO UPDATE SET
                    search_clicks=excluded.search_clicks,
                    search_impressions=excluded.search_impressions,
                    page_views=excluded.page_views,
                    page_requests=excluded.page_requests,
                    page_human=excluded.page_human,
                    page_bot=excluded.page_bot,
                    fetched_at=excluded.fetched_at
            ''', (domain, key, clicks, impressions, page_views, requests_, page_human, page_bot, now_iso))
            d += timedelta(days=1)
        con.commit()
        log(f'OK: {domain} updated {start} to {end}')

    con.close()


if __name__ == '__main__':
    main()
