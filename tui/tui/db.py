from __future__ import annotations

from pathlib import Path

from sqlalchemy import String, Integer, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Posting(Base):
    __tablename__ = "postings"

    url: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(String)
    company: Mapped[str | None] = mapped_column(String)
    platform: Mapped[str | None] = mapped_column(String)
    post_date: Mapped[str | None] = mapped_column(String)
    location_note: Mapped[str | None] = mapped_column(String)
    description_summary: Mapped[str | None] = mapped_column(String)
    first_seen: Mapped[str | None] = mapped_column(String)
    base_score: Mapped[int | None] = mapped_column(Integer)
    modifier: Mapped[int | None] = mapped_column(Integer)
    final_score: Mapped[int | None] = mapped_column(Integer)
    scoring_notes: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    selected_date: Mapped[str | None] = mapped_column(String)
    employment_type: Mapped[str | None] = mapped_column(String)
    applicant_count: Mapped[int | None] = mapped_column(Integer)

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.company, self.title) if p]
        return " · ".join(parts) if parts else self.url

    @property
    def display_date(self) -> str:
        if not self.first_seen:
            return "—"
        return self.first_seen[:10].replace("-", "/")


def make_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_postings(engine) -> list[Posting]:
    stmt = select(Posting).order_by(Posting.first_seen.desc())
    with Session(engine) as session:
        return list(session.scalars(stmt))
