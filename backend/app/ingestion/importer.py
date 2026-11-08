"""Import real public datasets (CSV) into BantayPondo.

Rules:
- `--source` must be a key in app/sources.py.
- Every row needs a reference link: either a `source_url` column (best: link to the
  project's own page) or `--file-url` (the exact URL you downloaded the file from).
- Rows without a valid link are REJECTED and written to a rejects file.

Usage:
  python -m app.ingestion.importer projects data/raw/dpwh.csv --source dpwh_transparency \
      --mapping data/mappings/dpwh_transparency.json --file-url "https://..."
  python -m app.ingestion.importer findings data/raw/coa_dpwh_2024.csv --source coa_audit_reports
"""
import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import AuditFinding, Project
from app.sources import SOURCES

URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.I)

PROJECT_FIELDS = [
    "project_code", "name", "category", "region", "province", "municipality",
    "implementing_office", "contractor", "abc", "contract_amount", "status", "progress",
    "start_date", "target_completion", "actual_completion", "lat", "lng", "source_url",
]
FINDING_FIELDS = ["agency", "year", "title", "text", "page", "source_url"]


class RejectedRow(ValueError):
    pass


def valid_url(u: str | None) -> bool:
    return bool(u and URL_RE.match(u.strip()))


def to_float(v):
    if v in (None, ""):
        return None
    return float(str(v).replace(",", "").replace("₱", "").replace("PHP", "").strip())


def to_date(v):
    if not v:
        return None
    s = str(v).replace(",", "").strip()
    if s.isdigit() and len(s) >= 12:  # epoch milliseconds (ArcGIS export)
        return datetime.fromtimestamp(int(s) / 1000, timezone.utc).date()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            continue
    return None


def map_row(row: dict, mapping: dict, fields: list[str]) -> dict:
    """mapping: {our_field: their_column}. Unmapped fields fall back to same name."""
    return {f: (row.get(mapping.get(f, f)) or "").strip() or None for f in fields}


def build_project(row: dict, source_key: str, file_url: str | None) -> Project:
    url = row["source_url"] or file_url
    if not valid_url(url):
        raise RejectedRow("missing/invalid source_url")
    if not row["project_code"] or not row["name"]:
        raise RejectedRow("missing project_code or name")
    status = (row["status"] or "").lower() or ("completed" if row["actual_completion"] else None)
    return Project(
        project_code=row["project_code"], name=row["name"], category=row["category"],
        region=row["region"], province=row["province"], municipality=row["municipality"],
        implementing_office=row["implementing_office"], contractor=row["contractor"],
        abc=to_float(row["abc"]), contract_amount=to_float(row["contract_amount"]),
        status=status, progress=to_float(row["progress"]),
        start_date=to_date(row["start_date"]), target_completion=to_date(row["target_completion"]),
        actual_completion=to_date(row["actual_completion"]),
        lat=to_float(row["lat"]), lng=to_float(row["lng"]),
        source_key=source_key, source_url=url.strip(), raw=row,
    )


def build_finding(row: dict, source_key: str, file_url: str | None) -> AuditFinding:
    url = row["source_url"] or file_url
    if not valid_url(url):
        raise RejectedRow("missing/invalid source_url")
    if not row["text"] or not row["year"]:
        raise RejectedRow("missing text or year")
    return AuditFinding(
        agency=row["agency"] or "DPWH", year=int(row["year"]), title=row["title"] or "",
        text=row["text"], page=int(row["page"]) if row["page"] else None,
        source_key=source_key, source_url=url.strip(),
    )


def import_csv(kind: str, path: str, source_key: str, mapping: dict | None = None,
               file_url: str | None = None, db=None) -> dict:
    if source_key not in SOURCES:
        raise SystemExit(f"Unknown source '{source_key}'. Add it to app/sources.py with its official URL.")
    if file_url and not valid_url(file_url):
        raise SystemExit("--file-url must be a valid http(s) link")
    mapping = mapping or {}
    fields, builder = (PROJECT_FIELDS, build_project) if kind == "projects" else (FINDING_FIELDS, build_finding)

    own_db = db is None
    db = db or SessionLocal()
    ok, rejects = 0, []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, raw in enumerate(csv.DictReader(f), start=2):
            try:
                db.add(builder(map_row(raw, mapping, fields), source_key, file_url))
                ok += 1
            except (RejectedRow, ValueError) as e:
                rejects.append({"line": i, "reason": str(e), **raw})
    db.commit()
    if own_db:
        db.close()

    if rejects:
        out = Path(path).with_suffix(".rejects.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rejects[0].keys()))
            w.writeheader()
            w.writerows(rejects)
    return {"imported": ok, "rejected": len(rejects)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["projects", "findings"])
    p.add_argument("path")
    p.add_argument("--source", required=True)
    p.add_argument("--mapping", help="JSON file: {our_field: their_column}")
    p.add_argument("--file-url", help="Exact URL the file was downloaded from")
    a = p.parse_args()
    init_db()
    mapping = json.loads(Path(a.mapping).read_text()) if a.mapping else None
    print(import_csv(a.kind, a.path, a.source, mapping, a.file_url))


if __name__ == "__main__":
    main()
