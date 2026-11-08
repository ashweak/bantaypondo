"""Rule-based red flags. These are signals FOR REVIEW, not proof of wrongdoing.
Each flag stores the source_urls of the records it is based on."""
import re
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Flag, Project

RULE_INFO = {
    "above_abc": "Contract cost is higher than the approved budget (ABC). Bids above the ABC are normally disqualified under RA 9184. It can also be a data-entry error, so check the official contract documents.",
    "contractor_concentration": "One contractor holds a large share of project value in this province.",
    "possible_duplicate": "The same work in the same town appears as several contracts (phases, packages or repeats). Often legitimate, but splitting contracts can avoid stricter bidding rules.",
    "status_inconsistency": "Reported status does not match reported progress or dates.",
    "overdue": "Project is past its target completion date but not marked completed.",
    "late_completion": "Project was finished long after its original target completion date.",
}


def _norm(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(phase|package|section|pkg|ph)\s*[ivx0-9]+\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _flag(p: Project, rule: str, severity: int, detail: str, urls: list[str], **extra) -> Flag:
    return Flag(project_id=p.id, rule=rule, severity=severity, detail=detail,
                evidence={"source_urls": sorted(set(urls)), **extra})


def compute_flags(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    db.execute(delete(Flag))
    projects = db.scalars(select(Project)).all()
    flags: list[Flag] = []

    for p in projects:
        # 1. Contract cost above the approved budget
        if p.abc and p.contract_amount and p.abc > 0:
            ratio = p.contract_amount / p.abc
            if ratio > settings.above_abc_ratio:
                flags.append(_flag(p, "above_abc", 3,
                                   f"Contract cost is {ratio - 1:.2%} above the ABC "
                                   f"(PHP {p.contract_amount - p.abc:,.2f} more).", [p.source_url], ratio=round(ratio, 5)))
        # 6. Finished long after target
        if p.actual_completion and p.target_completion:
            late = (p.actual_completion - p.target_completion).days
            if late > settings.late_days_low:
                flags.append(_flag(p, "late_completion", 2 if late > settings.late_days_high else 1,
                                   f"Finished {late} days after the original target ({p.target_completion}).",
                                   [p.source_url], days=late))
        # 4. Status inconsistency
        if p.status == "completed" and p.progress is not None and p.progress < 100:
            flags.append(_flag(p, "status_inconsistency", 3,
                               f"Marked completed but progress is {p.progress:.0f}%.", [p.source_url]))
        if p.start_date and p.actual_completion and p.actual_completion < p.start_date:
            flags.append(_flag(p, "status_inconsistency", 2,
                               "Completion date is earlier than start date.", [p.source_url]))
        # 5. Overdue
        if (p.target_completion and p.target_completion < today and not p.actual_completion
                and p.status not in ("completed", "terminated")):
            days = (today - p.target_completion).days
            flags.append(_flag(p, "overdue", 2 if days > 180 else 1,
                               f"{days} days past target completion ({p.target_completion}).", [p.source_url], days=days))

    # 2. Contractor concentration per province
    by_prov: dict[str, list[Project]] = defaultdict(list)
    for p in projects:
        if p.province and p.contractor and p.contract_amount:
            by_prov[p.province].append(p)
    for prov, items in by_prov.items():
        total = sum(p.contract_amount for p in items)
        by_c: dict[str, list[Project]] = defaultdict(list)
        for p in items:
            by_c[p.contractor.strip().upper()].append(p)
        for c, cp in by_c.items():
            share = sum(p.contract_amount for p in cp) / total
            if share >= settings.concentration_share and len(cp) >= settings.concentration_min_projects:
                urls = [p.source_url for p in cp]
                for p in cp:
                    flags.append(_flag(p, "contractor_concentration", 2,
                                       f"{p.contractor} holds {share:.0%} of project value in {prov} ({len(cp)} projects).",
                                       urls, share=round(share, 4), count=len(cp)))

    # 3. Possible duplicates (same municipality + normalized name)
    groups: dict[tuple, list[Project]] = defaultdict(list)
    for p in projects:
        if p.municipality:
            groups[(p.municipality.upper(), _norm(p.name))].append(p)
    for items in groups.values():
        codes = {p.project_code for p in items}
        if len(codes) > 1:
            urls = [p.source_url for p in items]
            for p in items:
                others = sorted(codes - {p.project_code})
                flags.append(_flag(p, "possible_duplicate", 1,
                                   f"Similar project(s) in same municipality: {', '.join(others)}.", urls, related=others))

    db.add_all(flags)
    db.commit()
    return len(flags)
