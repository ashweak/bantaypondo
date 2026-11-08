"""Builds one compact JSON snapshot used by the web GUI.

The same structure is served live at /api/snapshot and exported to static files
(python -m app.snapshot ../frontend/data/snapshot.json) for GitHub Pages hosting.
Every project keeps its reference link (as an index into `urls` to save space).
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Project
from app.rules.red_flags import RULE_INFO
from app.sources import SOURCES


def _near_abc_share(projects) -> float:
    from app.config import settings
    r = [p.contract_amount / p.abc for p in projects if p.abc and p.contract_amount]
    return round(sum(settings.near_abc_ratio <= x <= 1.0 for x in r) / len(r), 4) if r else 0.0


def build_snapshot(db: Session) -> dict:
    projects = db.scalars(select(Project).options(selectinload(Project.flags))).all()
    urls: list[str] = []
    url_idx: dict[str, int] = {}
    rows = []
    rule_counts: dict[str, int] = defaultdict(int)
    prov = defaultdict(lambda: {"projects": 0, "value": 0.0, "flagged": 0})
    contr = defaultdict(lambda: {"projects": 0, "value": 0.0, "flagged": 0, "provinces": set()})

    for p in projects:
        if p.source_url not in url_idx:
            url_idx[p.source_url] = len(urls)
            urls.append(p.source_url)
        flags = [[f.rule, f.severity, f.detail] for f in p.flags]
        score = sum(f[1] for f in flags)
        for r in {f[0] for f in flags}:
            rule_counts[r] += 1
        amt = p.contract_amount or 0
        if p.province:
            d = prov[p.province]
            d["projects"] += 1; d["value"] += amt; d["flagged"] += bool(flags)
        if p.contractor:
            c = contr[p.contractor.strip()]
            c["projects"] += 1; c["value"] += amt; c["flagged"] += bool(flags)
            if p.province:
                c["provinces"].add(p.province)
        rows.append({
            "id": p.id, "code": p.project_code, "name": p.name, "cat": p.category,
            "region": p.region, "prov": p.province, "muni": p.municipality,
            "office": p.implementing_office, "contractor": p.contractor,
            "abc": p.abc, "amount": p.contract_amount, "status": p.status,
            "start": p.start_date.isoformat() if p.start_date else None,
            "target": p.target_completion.isoformat() if p.target_completion else None,
            "done": p.actual_completion.isoformat() if p.actual_completion else None,
            "lat": p.lat, "lng": p.lng, "score": score, "flags": flags,
            "src": p.source_key, "u": url_idx[p.source_url],
        })

    rows.sort(key=lambda r: (-r["score"], -(r["amount"] or 0)))
    contractors = sorted(
        ({"name": k, **{**v, "provinces": len(v["provinces"])}} for k, v in contr.items()),
        key=lambda c: -c["value"])[:50]
    provinces = sorted(({"name": k, **v} for k, v in prov.items()), key=lambda x: -x["value"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": {
            "projects": len(rows),
            "value": sum(r["amount"] or 0 for r in rows),
            "flagged": sum(1 for r in rows if r["score"]),
            "contractors": len(contr),
            "provinces": len(prov),
            "near_abc_share": _near_abc_share(projects),
        },
        "rules": {k: {"meaning": v, "count": rule_counts.get(k, 0)} for k, v in RULE_INFO.items()},
        "sources": SOURCES,
        "urls": urls,
        "provinces": provinces,
        "contractors": contractors,
        "projects": rows,
    }


if __name__ == "__main__":
    from app.db import SessionLocal, init_db
    init_db()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/data/snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        snap = build_snapshot(db)
    out.write_text(json.dumps(snap, separators=(",", ":"), default=str))
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB, {snap['stats']['projects']} projects)")
