# BantayPondo 🇵🇭

AI agent watchdog for public infrastructure spending. Agents flag projects **for review**, explain them in Taglish, and **link every claim to an official source**.

> ⚠️ Flags are signals for review, **not proof of wrongdoing**. Always verify with the linked source.

## Data sources (official, public)

| Key | Source | Link | What it gives |
|---|---|---|---|
| `dpwh_transparency` | DPWH Transparency Portal | https://transparency.dpwh.gov.ph/ | All DPWH projects since 2016: cost, contractor, office, progress, location, documents |
| `sumbong_sa_pangulo` | Sumbong sa Pangulo | https://sumbongsapangulo.ph/ | Flood control projects: location, contractor, cost, completion |
| `philgeps_open_data` | PhilGEPS Open Data | https://philgeps.gov.ph/CmsHomePages/open-data | Bid & award notices (ABC, awardee, amount) |
| `coa_audit_reports` | COA Annual Audit Reports | https://www.coa.gov.ph/ | Audit findings per agency |
| `dbm_gaa` | DBM – GAA | https://www.dbm.gov.ph/ | Approved budget line items |
| `foi_dpwh` | FOI Portal – DPWH | https://foi.gov.ph/agencies/dpwh/ | Datasets released via FOI |

### Source-link rules (enforced in code)
1. A record is accepted only if it has a valid `source_url` (link to the project page) **or** you pass `--file-url` (the exact download link of the file).
2. Rows without a link go to `*.rejects.csv`, not the DB.
3. The database itself rejects records without an http(s) link (CHECK constraint).
4. Every red flag stores the `source_urls` it was computed from.
5. Every chat answer ends with numbered reference links. No matching records = no claims.
6. Only sources listed in `app/sources.py` are allowed.

## Agents
```
supervisor ─┬─> analyst      (flagged projects, risk score)
            ├─> contractors  (top contractors by value)
            └─> auditor      (COA findings search)
                    └─> explainer (Taglish answer + citations + disclaimer)
```
Works without an API key (template answers). Add `GEMINI_API_KEY` for AI explanations.

## Red-flag rules
| Rule | Severity | Meaning |
|---|---|---|
| `above_abc` | 3 | Contract cost > approved budget by more than 0.1% (bids above ABC are normally disqualified under RA 9184; can also be a data-entry error) |
| `contractor_concentration` | 2 | One contractor ≥ 30% of value in a province (≥ 5 projects) |
| `late_completion` | 1–2 | Finished > 90 days (2 if > 180) after the original target |
| `possible_duplicate` | 1 | Same work in the same town split into several contracts/phases |
| `status_inconsistency` | 3 | "Completed" but progress < 100%, or impossible dates |
| `overdue` | 1–2 | Past target completion, not completed |

**Program-wide insight (not a per-project flag):** in the flood control list, 55.3% of contracts were awarded within 0.1% of the approved budget. Flagging each one would make flags meaningless, so it's shown as a headline stat.

Thresholds are in `app/config.py`.

## Web GUI
`frontend/` is a single-page site (Leaflet map, filters, project details, agent chat).
- **Live mode:** run the backend and open http://localhost:8000. Chat uses the LangGraph agents (+ Gemini if `GEMINI_API_KEY` is set).
- **Static mode:** if no backend is found it loads `frontend/data/snapshot.json` and runs the same routing logic in the browser. This is what the GitHub Pages demo uses.

Rebuild the static snapshot after importing data:
```bash
cd backend && python -m app.snapshot ../frontend/data/snapshot.json
```

## Setup
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY (optional)
uvicorn app.main:app --reload   # http://localhost:8000/docs
pytest -q
```

## Loading real data
1. Download/export a dataset from one of the sources above into `backend/data/raw/`.
2. Copy `data/mappings/example_mapping.json`, edit the right-hand side to match the real CSV headers.
3. Import:
```bash
python -m app.ingestion.importer projects data/raw/dpwh.csv \
  --source dpwh_transparency --mapping data/mappings/dpwh.json \
  --file-url "https://<exact link you downloaded from>"
curl -X POST localhost:8000/api/flags/recompute
```
COA findings (one row per finding: agency, year, title, text, page, source_url):
```bash
python -m app.ingestion.importer findings data/raw/coa_dpwh_2024.csv --source coa_audit_reports
```

## API
- `GET /api/sources`: official sources
- `GET /api/projects?province=&contractor=&flagged_only=true`
- `GET /api/projects/{id}`: with flags + evidence links
- `POST /api/flags/recompute`
- `POST /api/chat` `{"question": "Show suspicious projects in Bulacan"}`

## Roadmap
- Phase 2: pgvector RAG over COA PDFs, citizen photo upload + vision check (human-reviewed)
- Phase 3: Next.js map + chat UI, satellite imagery check, alerts

## Legal & ethics
- Respect each site's terms of use; prefer official exports/FOI over heavy scraping.
- Never label a person/company as corrupt. Use "flagged for review."
- Citizen uploads must be moderated before publishing.
