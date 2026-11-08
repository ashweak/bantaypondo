"""Multi-agent workflow (LangGraph):

    supervisor -> analyst | contractors | auditor -> explainer

Hard rule: the explainer may only use records returned by the tools, and every
answer ends with numbered reference links. No records -> no claims.
"""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.llm import generate
from app.models import AuditFinding, Flag, Project
from app.rules.red_flags import RULE_INFO

DISCLAIMER = ("Paalala: Ito ay mga palatandaan para suriin (flags for review), hindi patunay ng katiwalian. "
              "Always verify using the linked official sources.")


class State(TypedDict, total=False):
    question: str
    route: str
    province: str | None
    contractor: str | None
    records: list[dict]
    answer: str
    citations: list[dict]
    steps: list[str]


def _db(config) -> Session:
    return config["configurable"]["db"]


# ---------- Supervisor ----------
def supervisor(state: State, config) -> State:
    db = _db(config)
    q = state["question"]
    provinces = [p for p in db.scalars(select(Project.province).distinct()).all() if p]
    ql_ = q.lower()

    def mentioned(name: str) -> bool:
        return len(name) > 2 and re.search(r"\b" + re.escape(name.lower()) + r"\b", ql_) is not None

    province = next((p for p in sorted(provinces, key=len, reverse=True) if mentioned(p)), None)
    contractors = [c for c in db.scalars(select(Project.contractor).distinct()).all() if c]
    contractor = next((c for c in sorted(contractors, key=len, reverse=True) if mentioned(c)), None)

    route = None
    llm = generate(
        f'Classify this question into one of: "flags", "contractors", "audit". '
        f'Reply with JSON like {{"route": "flags"}} only.\nQuestion: {q}')
    if llm:
        m = re.search(r'"route"\s*:\s*"(\w+)"', llm)
        route = m.group(1) if m and m.group(1) in ("flags", "contractors", "audit") else None
    if not route:  # keyword fallback
        ql = q.lower()
        if any(k in ql for k in ("coa", "audit", "finding", "report")):
            route = "audit"
        elif any(k in ql for k in ("contractor", "kontratista", "top", "sino")) and not contractor:
            route = "contractors"
        else:
            route = "flags"
    return {"route": route, "province": province, "contractor": contractor,
            "steps": [f"supervisor -> {route} (province={province}, contractor={contractor})"]}


# ---------- Worker agents ----------
def analyst(state: State, config) -> State:
    db = _db(config)
    stmt = (select(Project, func.sum(Flag.severity).label("score"))
            .join(Flag).group_by(Project.id).order_by(func.sum(Flag.severity).desc()).limit(10))
    if state.get("province"):
        stmt = stmt.where(Project.province == state["province"])
    if state.get("contractor"):
        stmt = stmt.where(Project.contractor == state["contractor"])
    records = []
    for p, score in db.execute(stmt).all():
        records.append({
            "type": "project", "project_code": p.project_code, "name": p.name,
            "province": p.province, "contractor": p.contractor, "contract_amount": p.contract_amount,
            "status": p.status, "risk_score": int(score),
            "flags": [{"rule": f.rule, "detail": f.detail, "meaning": RULE_INFO.get(f.rule)} for f in p.flags],
            "source_url": p.source_url,
        })
    return {"records": records, "steps": state["steps"] + [f"analyst: {len(records)} flagged projects"]}


def contractors(state: State, config) -> State:
    db = _db(config)
    stmt = (select(Project.contractor, func.count(Project.id), func.sum(Project.contract_amount),
                   func.min(Project.source_url))
            .where(Project.contractor.is_not(None))
            .group_by(Project.contractor).order_by(func.sum(Project.contract_amount).desc()).limit(10))
    if state.get("province"):
        stmt = stmt.where(Project.province == state["province"])
    records = []
    for name, count, total, _ in db.execute(stmt).all():
        urls_stmt = select(Project.source_url).where(Project.contractor == name).limit(5)
        if state.get("province"):
            urls_stmt = urls_stmt.where(Project.province == state["province"])
        urls = db.scalars(urls_stmt).all()
        records.append({"type": "contractor", "contractor": name, "projects": count,
                        "total_amount": total, "source_url": urls[0], "more_sources": urls[1:]})
    return {"records": records, "steps": state["steps"] + [f"contractors: {len(records)} rows"]}


def auditor(state: State, config) -> State:
    """Keyword retrieval over COA findings. (Phase 2: swap for pgvector embeddings.)"""
    db = _db(config)
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", state["question"].lower())
             if w not in {"what", "show", "audit", "findings", "report", "about", "with"}]
    stmt = select(AuditFinding)
    if words:
        stmt = stmt.where(or_(*[AuditFinding.text.ilike(f"%{w}%") for w in words],
                              *[AuditFinding.title.ilike(f"%{w}%") for w in words]))
    rows = db.scalars(stmt.order_by(AuditFinding.year.desc()).limit(8)).all()
    records = [{"type": "audit_finding", "agency": r.agency, "year": r.year, "title": r.title,
                "excerpt": r.text[:600], "page": r.page, "source_url": r.source_url} for r in rows]
    return {"records": records, "steps": state["steps"] + [f"auditor: {len(records)} findings"]}


# ---------- Explainer ----------
def _citations(records: list[dict]) -> list[dict]:
    cites, seen = [], set()
    for r in records:
        for u in [r["source_url"], *r.get("more_sources", [])]:
            if u not in seen:
                seen.add(u)
                label = r.get("name") or r.get("title") or r.get("contractor") or u
                cites.append({"n": len(cites) + 1, "label": label, "url": u})
    return cites


def _fallback_text(state: State) -> str:
    recs = state["records"]
    lines = []
    for i, r in enumerate(recs, 1):
        if r["type"] == "project":
            fl = "; ".join(f["detail"] for f in r["flags"])
            lines.append(f"- {r['name']} ({r['project_code']}, {r['province']}) - risk {r['risk_score']}: {fl}")
        elif r["type"] == "contractor":
            lines.append(f"- {r['contractor']}: {r['projects']} projects, PHP {r['total_amount'] or 0:,.2f}")
        else:
            lines.append(f"- COA {r['year']} - {r['title']}: {r['excerpt'][:200]}...")
    return "\n".join(lines)


def explainer(state: State, config) -> State:
    recs = state.get("records", [])
    if not recs:
        return {"answer": "Walang nakitang datos na tugma sa tanong sa ating database. "
                          "No matching records were found, so no claims are made.",
                "citations": [], "steps": state["steps"] + ["explainer: no data"]}
    cites = _citations(recs)
    url_to_n = {c["url"]: c["n"] for c in cites}
    for r in recs:
        r["ref"] = url_to_n[r["source_url"]]

    text = generate(
        prompt=f"Question: {state['question']}\n\nRecords (JSON):\n{json.dumps(recs, default=str)[:12000]}",
        system=("You are BantayPondo's explainer. Answer in clear Taglish. Use ONLY the records given. "
                "Cite each fact with its [ref] number. Never accuse anyone of a crime; describe items as "
                "'flags for review'. If records don't answer the question, say so."),
    ) or _fallback_text(state)
    return {"answer": f"{text}\n\n{DISCLAIMER}", "citations": cites,
            "steps": state["steps"] + ["explainer: done"]}


def build_graph():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    g.add_node("analyst", analyst)
    g.add_node("contractors", contractors)
    g.add_node("auditor", auditor)
    g.add_node("explainer", explainer)
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", lambda s: s["route"],
                            {"flags": "analyst", "contractors": "contractors", "audit": "auditor"})
    for n in ("analyst", "contractors", "auditor"):
        g.add_edge(n, "explainer")
    g.add_edge("explainer", END)
    return g.compile()


GRAPH = build_graph()


def ask(question: str, db: Session) -> dict[str, Any]:
    out = GRAPH.invoke({"question": question, "steps": []}, config={"configurable": {"db": db}})
    return {"answer": out["answer"], "citations": out["citations"], "steps": out["steps"],
            "route": out["route"]}
