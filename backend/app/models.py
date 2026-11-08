from datetime import date, datetime, timezone


def _now():
    return datetime.now(timezone.utc)

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Every data table requires a non-empty https source_url (enforced in DB + ingestion).
URL_CHECK = "source_url LIKE 'https://%' OR source_url LIKE 'http://%'"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(URL_CHECK, name="project_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(64), index=True)
    province: Mapped[str | None] = mapped_column(String(64), index=True)
    municipality: Mapped[str | None] = mapped_column(String(128))
    implementing_office: Mapped[str | None] = mapped_column(String(128))
    contractor: Mapped[str | None] = mapped_column(String(255), index=True)
    abc: Mapped[float | None] = mapped_column(Float)              # Approved Budget for the Contract
    contract_amount: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[float | None] = mapped_column(Float)          # 0-100
    start_date: Mapped[date | None] = mapped_column(Date)
    target_completion: Mapped[date | None] = mapped_column(Date)
    actual_completion: Mapped[date | None] = mapped_column(Date)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    source_key: Mapped[str] = mapped_column(String(64))           # key in app.sources.SOURCES
    source_url: Mapped[str] = mapped_column(Text, nullable=False)  # link to this exact record/page/file
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    raw: Mapped[dict | None] = mapped_column(JSON)

    flags: Mapped[list["Flag"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class AuditFinding(Base):
    __tablename__ = "audit_findings"
    __table_args__ = (CheckConstraint(URL_CHECK, name="finding_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(64), default="coa_audit_reports")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    rule: Mapped[str] = mapped_column(String(64))
    severity: Mapped[int] = mapped_column(Integer)  # 1 low - 3 high
    detail: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)  # includes source_urls used

    project: Mapped[Project] = relationship(back_populates="flags")
