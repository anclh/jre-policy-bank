# JRE Policy Bank · JRE 政策資料庫

Interview-oriented Hong Kong policy / current-affairs bank for civil-service JRE prep.

**Live (GitHub Pages):** https://anclh.github.io/jre-policy-bank/

Public sources only (`info.gov.hk`). Not affiliated with CS Radar.

## Local

```bash
cd docs && python3 -m http.server 8877
# open http://127.0.0.1:8877/
```

## Refresh

```bash
python3 scripts/refresh_policies.py
cp data/policies.json docs/data/policies.json
```
