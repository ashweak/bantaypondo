"""Weekly refresh from the official DPWH Transparency Portal API.

- Fetches project listings politely (honest User-Agent, ~3 s between requests,
  backs off on 429). It does NOT spoof browsers or rotate proxies: if DPWH
  blocks automated access, the job stops and the site keeps its last good data.
- Keeps flood control projects only.
- Each record's reference link is its official API record:
  https://api.transparency.dpwh.gov.ph/projects/{contractId}
- Fills the approved budget (ABC) and original target date from the
  community mirror CSV by contract ID, because the API listing may not have them.

Usage:
  python -m app.ingestion.dpwh_api --mirror data/raw/flood_control.csv \
      --mapping data/mappings/hf_flood_control_mirror.json --out data/raw/merged.csv
Exit code 2 = API unavailable/blocked (caller should keep the old snapshot).
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import httpx

API = "https://api.transparency.dpwh.gov.ph/projects"
RECORD_URL = API + "/{}"
MIRROR_URL = ("https://huggingface.co/datasets/chrisandrei/DPWH_Flood_Control_2018-2025_Projects/"
              "resolve/main/flood-control-projects-visual_2025-11-08.csv")
HEADERS = {
    "User-Agent": "BantayPondo/1.0 (weekly public-data refresh; +https://github.com/ashweak/bantaypondo)",
    "Accept": "application/json",
    "Origin": "https://transparency.dpwh.gov.ph",
    "Referer": "https://transparency.dpwh.gov.ph/",
}
FIELDS = ["project_code", "name", "category", "region", "province", "municipality",
          "implementing_office", "contractor", "abc", "contract_amount", "status", "progress",
          "start_date", "target_completion", "actual_completion", "lat", "lng",
          "source_url", "source_key"]


class Blocked(RuntimeError):
    pass


def _records(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    d = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(d, dict) and isinstance(d.get("data"), list):
        return d["data"]
    for k in ("data", "results", "items"):
        if isinstance(payload.get(k), list):
            return payload[k]
    return []


def fetch_all(limit: int = 5000, max_pages: int = 80, delay: float = 3.0, client=None) -> list[dict]:
    client = client or httpx.Client(headers=HEADERS, timeout=120, follow_redirects=True)
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        for attempt in range(4):
            r = client.get(API, params={"page": page, "limit": limit})
            if r.status_code == 429:
                time.sleep(60 * (attempt + 1))
                continue
            break
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("application/json"):
            raise Blocked(f"page {page}: HTTP {r.status_code} ({ctype or 'no content-type'})")
        rows = _records(r.json())
        if not rows:
            break
        out.extend(rows)
        print(f"page {page}: {len(rows)} records (total {len(out)})", flush=True)
        if len(rows) < limit:
            break
        time.sleep(delay)
    if not out:
        raise Blocked("API returned no records")
    return out


def _get(rec: dict, *keys):
    for k in keys:
        v = rec
        for part in k.split("."):
            v = v.get(part) if isinstance(v, dict) else None
        if v not in (None, ""):
            return v
    return None


def is_flood(rec: dict) -> bool:
    cats = " ".join(str(_get(rec, k) or "") for k in ("category", "componentCategories"))
    if re.search(r"flood", cats, re.I):
        return True
    return bool(re.search(r"flood control|flood mitigation|revetment|dike|seawall|sea wall",
                          str(_get(rec, "description") or ""), re.I))


def normalize(rec: dict) -> dict | None:
    code = _get(rec, "contractId", "contract_id", "id")
    name = _get(rec, "description", "projectDescription", "name")
    if not code or not name:
        return None
    contractor = _get(rec, "contractor", "contractor.name", "contractorName")
    if isinstance(contractor, str):
        contractor = re.sub(r"\s*\(\d+\)\s*$", "", contractor).strip()  # drop "(23426)" IDs
    loc = _get(rec, "location")
    region = _get(rec, "location.region", "region")
    province = _get(rec, "location.province", "province")
    if isinstance(loc, str) and not region:
        region = loc.split(",")[-1].strip()
    parts = [p.strip() for p in str(name).split(",") if p.strip()]
    municipality = _get(rec, "location.municipality", "municipality") or (parts[-2] if len(parts) >= 3 else None)
    status = (str(_get(rec, "status") or "")).strip().lower() or None
    completion = _get(rec, "completionDate", "completion_date")
    done = status == "completed"
    return {
        "project_code": str(code).strip(), "name": str(name).strip(),
        "category": _get(rec, "category"), "region": region, "province": province,
        "municipality": municipality, "implementing_office": _get(rec, "implementingOffice", "location.deo"),
        "contractor": contractor, "abc": _get(rec, "abc", "approvedBudget"),
        "contract_amount": _get(rec, "budget", "contractCost", "contractAmount"),
        "status": status, "progress": _get(rec, "progress"),
        "start_date": _get(rec, "startDate"), "target_completion": None if done else completion,
        "actual_completion": completion if done else None,
        "lat": _get(rec, "latitude", "lat"), "lng": _get(rec, "longitude", "lng", "lon"),
        "source_url": RECORD_URL.format(str(code).strip()), "source_key": "dpwh_transparency",
    }


def load_mirror(path: str, mapping: dict) -> dict[str, dict]:
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            row = {k: (raw.get(mapping.get(k, k)) or "").strip() or None for k in FIELDS}
            if row["project_code"]:
                row["source_url"], row["source_key"] = MIRROR_URL, "hf_flood_control_mirror"
                out[row["project_code"]] = row
    return out


def merge(api_rows: list[dict], mirror: dict[str, dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for rec in api_rows:
        if not is_flood(rec):
            continue
        row = normalize(rec)
        if not row:
            continue
        m = mirror.get(row["project_code"])
        if m:  # official record wins; mirror fills the gaps (ABC, original target, location)
            for k in ("abc", "target_completion", "municipality", "province", "implementing_office", "lat", "lng"):
                if not row.get(k) and m.get(k):
                    row[k] = m[k]
            if not row.get("actual_completion") and m.get("actual_completion") and row["status"] == "completed":
                row["actual_completion"] = m["actual_completion"]
        merged[row["project_code"]] = row
    for code, m in mirror.items():  # keep mirror-only projects (e.g. removed from listing)
        merged.setdefault(code, m)
    return list(merged.values())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mirror", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    mirror = load_mirror(a.mirror, json.loads(Path(a.mapping).read_text()))
    try:
        api_rows = fetch_all()
    except (Blocked, httpx.HTTPError) as e:
        print(f"DPWH API unavailable: {e}", file=sys.stderr)
        sys.exit(2)
    rows = merge(api_rows, mirror)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    official = sum(r["source_key"] == "dpwh_transparency" for r in rows)
    print(f"wrote {a.out}: {len(rows)} flood control projects ({official} from the official API)")


if __name__ == "__main__":
    main()
