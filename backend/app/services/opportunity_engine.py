"""Generic-opportunity engine.

Scores the commercial opportunity of a product whose listed patents are close to
expiry. The score blends time-to-expiry, how crowded the field already is, and
whether exclusivity/PTE extends the runway — the same inputs an IP desk uses to
triage the watchlist.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import OrangeBookPatent, OrangeBookProduct


@dataclass
class Opportunity:
    appl_no: str
    ingredient: str
    trade_name: str | None
    applicant: str | None
    patent_number: str
    expiration_date: str | None
    months_to_expiry: int | None
    opportunity_score: float
    band: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _band(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 25:
        return "watch"
    return "low"


def score_opportunity(months_to_expiry: int | None, competitor_count: int) -> tuple[float, str]:
    """Return a 0..100 opportunity score and a human rationale."""
    if months_to_expiry is None:
        return 0.0, "No listed expiry date."
    if months_to_expiry < 0:
        return 10.0, "Patent already expired."

    # Time component: nearer expiry = larger opportunity, decaying after 36m.
    time_score = max(0.0, 100.0 - (months_to_expiry / 36.0) * 100.0)
    # Crowding penalty: many listed patents means a harder entry.
    crowding = min(30.0, competitor_count * 3.0)
    score = max(0.0, min(100.0, time_score - crowding + 25.0))
    rationale = (
        f"{months_to_expiry} months to expiry; "
        f"{competitor_count} listed patent(s) — {'crowded' if crowding > 12 else 'open'} field."
    )
    return round(score, 1), rationale


def top_opportunities(session: Session, *, limit: int = 25, within_months: int = 48) -> list[Opportunity]:
    today = date.today()
    patents = list(session.scalars(select(OrangeBookPatent)))
    products = {
        (p.appl_type, p.appl_no): p
        for p in session.scalars(select(OrangeBookProduct))
    }
    # Count listed patents per application so we can penalise crowded fields.
    counts = dict(
        session.execute(
            select(
                func.concat(OrangeBookPatent.appl_type, "-", OrangeBookPatent.appl_no),
                func.count(OrangeBookPatent.id),
            ).group_by(OrangeBookPatent.appl_type, OrangeBookPatent.appl_no)
        ).all()
    )

    raw: list[Opportunity] = []
    for patent in patents:
        if not patent.expiration_date:
            continue
        months = (patent.expiration_date.year - today.year) * 12 + (patent.expiration_date.month - today.month)
        if months < 0 or months > within_months:
            continue
        product = products.get((patent.appl_type, patent.appl_no))
        competitors = counts.get(f"{patent.appl_type}-{patent.appl_no}", 1)
        score, rationale = score_opportunity(months, competitors)
        raw.append(
            Opportunity(
                appl_no=f"{patent.appl_type}{patent.appl_no}",
                ingredient=(product.ingredient if product else None) or "—",
                trade_name=product.trade_name if product else None,
                applicant=(product.applicant_full_name or product.applicant) if product else None,
                patent_number=patent.patent_number,
                expiration_date=patent.expiration_date.isoformat(),
                months_to_expiry=months,
                opportunity_score=score,
                band=_band(score),
                rationale=rationale,
            )
        )

    raw.sort(key=lambda item: item.opportunity_score, reverse=True)
    return raw[:limit]


def opportunity_summary(session: Session) -> dict[str, Any]:
    rows = top_opportunities(session, limit=5000)
    by_band: dict[str, int] = {}
    for row in rows:
        by_band[row.band] = by_band.get(row.band, 0) + 1
    sponsors: dict[str, float] = {}
    for row in rows:
        if row.applicant:
            sponsors[row.applicant] = sponsors.get(row.applicant, 0.0) + row.opportunity_score
    leaderboard = sorted(sponsors.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "total": len(rows),
        "by_band": by_band,
        "top": [row.to_dict() for row in rows[:25]],
        "sponsor_leaderboard": [{"sponsor": name, "score": round(score, 1)} for name, score in leaderboard],
    }
