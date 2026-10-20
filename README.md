# JRE Policy Bank · JRE 政策資料庫

Interview-oriented Hong Kong **policy / current-affairs** MVP for civil-service style prep (JRE).

Modeled after the *idea* of a searchable interview current-affairs bank (keyword search, department tags, summaries, interview questions, weekly digest) — **not** a copy of any paid product. All seed items link to **public** HKSAR Government press releases (`info.gov.hk`) and related official pages. Summaries and interview angles are **original** editorial notes for practice.

## Features (MVP)

1. Keyword search across title, summary, tags, departments  
2. Filter chips by bureau/department and policy theme  
3. Policy cards: date, title, departments, themes, one-paragraph summary, public source link  
4. 2–3 interview-oriented angles/questions per card  
5. Weekly digest view (last 14 days grouped by department)  
6. Bilingual UI (Traditional Chinese + English), mobile-friendly, no login  

## Open / serve

Prefer a local static server so `fetch('data/policies.json')` works reliably (some browsers block `file://` fetch).

```bash
cd /workspace/jre-policy-bank
python3 -m http.server 8877
```

Then open: **http://127.0.0.1:8877/**

Or on the box with a reachable bind:

```bash
cd /workspace/jre-policy-bank && python3 -m http.server 8877 --bind 0.0.0.0
```

## Project layout

```
jre-policy-bank/
├── index.html
├── css/styles.css
├── js/app.js
├── data/policies.json
├── scripts/
│   ├── refresh_policies.py
│   └── last_refresh.json
└── README.md
```

## Data shape

Each item in `data/policies.json`:

- `id`, `date` (YYYY-MM-DD)
- `title`, optional `title_en`
- `departments[]`, `themes[]`
- `summary`
- `interview_angles[]`
- `source_url`, `source_name`

## Daily refresh (info.gov.hk)

Pull recent public HKSAR press releases, keep policy-relevant items, draft Traditional Chinese summaries + interview angles, and merge into `data/policies.json` (deduped by `source_url` / nearby P-ids / title fingerprint).

```bash
cd /workspace/jre-policy-bank
python3 scripts/refresh_policies.py
```

Useful flags:

```bash
python3 scripts/refresh_policies.py --days 7 --max-new 10
python3 scripts/refresh_policies.py --dry-run
```

- Sources: Chinese day indexes `https://www.info.gov.hk/gia/general/YYYYMM/DDc.htm` (fallback to `DD.htm` / `today.htm`)
- Filters out lifestyle / sports / beaches / routine enforcement fluff
- Writes run log to `scripts/last_refresh.json`
- Does **not** touch paid sites (e.g. CS Radar)
- Static server on port **8877** can keep running; reload the browser after refresh

Still open: cron/systemd timer scheduling; dedicated LegCo bills scraper; digest remains client-side last-14-days.

## Licence / ethics

Use only public government sources. Do **not** scrape or reproduce CS Radar or other paid content.
