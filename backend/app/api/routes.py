from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import ask
from app.db import get_db
from app.models import Flag, Project
from app.rules.red_flags import RULE_INFO, compute_flags
from app.snapshot import build_snapshot
from app.sources import SOURCES

router = APIRouter()


def project_out(p: Project, score: int | None = None) -> dict:
    return {
        "id": p.id, "project_code": p.project_code, "name": p.name, "category": p.category,
        "region": p.region, "province": p.province, "municipality": p.municipality,
        "contractor": p.contractor, "abc": p.abc, "contract_amount": p.contract_amount,
        "status": p.status, "progress": p.progress, "lat": p.lat, "lng": p.lng,
        "risk_score": score, "source": SOURCES.get(p.source_key, {}).get("name"),
        "source_url": p.source_url, "retrieved_at": p.retrieved_at,
    }


_snap_cache: dict = {}


@router.get("/snapshot")
def snapshot(db: Session = Depends(get_db)):
    """Everything the GUI needs, in one call (cached until flags are recomputed)."""
    if "data" not in _snap_cache:
        _snap_cache["data"] = build_snapshot(db)
    return _snap_cache["data"]


@router.get("/sources")
def list_sources():
    return SOURCES


@router.get("/projects")
def list_projects(province: str | None = None, contractor: str | None = None,
                  flagged_only: bool = False, limit: int = 100, db: Session = Depends(get_db)):
    score = func.coalesce(func.sum(Flag.severity), 0).label("score")
    stmt = select(Project, score).outerjoin(Flag).group_by(Project.id).order_by(score.desc()).limit(min(limit, 500))
    if province:
        stmt = stmt.where(Project.province == province)
    if contractor:
        stmt = stmt.where(Project.contractor == contractor)
    if flagged_only:
        stmt = stmt.having(func.count(Flag.id) > 0)
    return [project_out(p, int(s)) for p, s in db.execute(stmt).all()]


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    out = project_out(p, sum(f.severity for f in p.flags))
    out["flags"] = [{"rule": f.rule, "meaning": RULE_INFO[f.rule], "severity": f.severity,
                     "detail": f.detail, "evidence": f.evidence} for f in p.flags]
    return out


@router.post("/flags/recompute")
def recompute(db: Session = Depends(get_db)):
    n = compute_flags(db)
    _snap_cache.clear()
    return {"flags": n}


class ChatIn(BaseModel):
    question: str


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    if not body.question.strip():
        raise HTTPException(400, "Empty question")
    return ask(body.question, db)
