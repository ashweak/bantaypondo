"""TEST-ONLY synthetic fixtures. These are NOT real projects and are never loaded into
the real database. They exist only to check the rules and the source-link enforcement."""
import csv
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.agents.graph import ask
from app.db import Base
from app.ingestion.importer import import_csv
from app.models import Flag, Project
from app.rules.red_flags import compute_flags

T = "https://example.org/TEST-ONLY/"


@pytest.fixture
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def row(code, **kw):
    base = dict(project_code=code, name=f"Test Flood Control {code}", province="TestProv",
                municipality="TestTown", contractor="TEST CO A", abc="1000000",
                contract_amount="500000", status="ongoing", progress="50",
                start_date="2025-01-01", target_completion="2027-01-01", actual_completion="",
                source_url=T + code)
    base.update(kw)
    return base


def test_rows_without_link_are_rejected(db, tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [row("A1"), row("A2", source_url=""), row("A3", source_url="not-a-url")])
    res = import_csv("projects", str(p), "dpwh_transparency", db=db)
    assert res == {"imported": 1, "rejected": 2}
    assert (tmp_path / "x.rejects.csv").exists()


def test_file_url_fallback(db, tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [row("B1", source_url="")])
    res = import_csv("projects", str(p), "dpwh_transparency", file_url=T + "file.csv", db=db)
    assert res["imported"] == 1
    assert db.scalar(select(Project.source_url)) == T + "file.csv"


def test_unknown_source_blocked(db, tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [row("C1")])
    with pytest.raises(SystemExit):
        import_csv("projects", str(p), "random_blog", db=db)


def test_db_constraint_blocks_missing_link(db):
    db.add(Project(project_code="Z", name="Z", source_key="dpwh_transparency", source_url="nope"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_red_flags(db, tmp_path):
    rows = [
        row("D1", contract_amount="1050000"),                        # above ABC
        row("D6", target_completion="2025-03-01", actual_completion="2025-12-01"),  # late
        row("D2", status="completed", progress="40"),                # inconsistent
        row("D3", target_completion="2025-02-01"),                   # overdue
        row("D4", name="Test Flood Control Seawall Phase I"),
        row("D5", name="Test Flood Control Seawall Phase II"),       # possible duplicate
    ]
    write_csv(tmp_path / "x.csv", rows)
    import_csv("projects", str(tmp_path / "x.csv"), "dpwh_transparency", db=db)
    compute_flags(db, today=date(2026, 11, 8))
    rules = {(f.project.project_code, f.rule) for f in db.scalars(select(Flag))}
    assert ("D1", "above_abc") in rules
    assert ("D6", "late_completion") in rules
    assert ("D2", "status_inconsistency") in rules
    assert ("D3", "overdue") in rules
    assert ("D4", "possible_duplicate") in rules
    assert ("D1", "contractor_concentration") in rules  # 6 projects, 100% share
    for f in db.scalars(select(Flag)):
        assert f.evidence["source_urls"], "every flag must carry source links"


def test_chat_always_cites(db, tmp_path):
    write_csv(tmp_path / "x.csv", [row("E1", contract_amount="1200000")])
    import_csv("projects", str(tmp_path / "x.csv"), "dpwh_transparency", db=db)
    compute_flags(db)
    out = ask("Show suspicious projects in TestProv", db)
    assert out["route"] == "flags"
    assert out["citations"] and out["citations"][0]["url"].startswith("https://")
    assert "flags for review" in out["answer"]


def test_chat_no_data_makes_no_claims(db):
    out = ask("Show suspicious projects", db)
    assert out["citations"] == []
    assert "no claims" in out["answer"].lower()
