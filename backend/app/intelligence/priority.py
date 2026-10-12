"""Priority scoring for insights and alerts.

Score = weighted sum of six signals, clamped to 0-100:

  patent importance   (25)  — patent breadth, use codes, blockbuster indicators
  sponsor importance  (15)  — market weight of the affected company
  revenue potential   (20)  — commercial size implied by the product
  market competition  (15)  — number of challengers / ANDA filers
  exclusivity impact  (15)  — effect on remaining market exclusivity
  recency             (10)  — how fresh the event is

Bands: Critical 90-100, High 70-89, Medium 40-69, Low 0-39.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.text import normalize_name

WEIGHTS = {
    "patent_importance": 25,
    "sponsor_importance": 15,
    "revenue_potential": 20,
    "market_competition": 15,
    "exclusivity_impact": 15,
    "recency": 10,
}

# Sponsors with outsized market weight. A production deployment loads this from
# a managed reference table; the default set covers the largest innovators.
MAJOR_SPONSORS: frozenset[str] = frozenset(
    normalize_name(name)
    for name in (
        "Pfizer", "Merck", "Johnson & Johnson", "AbbVie", "Bristol-Myers Squibb",
        "Eli Lilly", "Novartis", "Roche", "AstraZeneca", "GlaxoSmithKline", "GSK",
        "Sanofi", "Bayer", "Boehringer Ingelheim", "Takeda", "Amgen", "Gilead Sciences",
        "Biogen", "Regeneron", "Vertex Pharmaceuticals", "Moderna", "Novo Nordisk",
        "Teva", "Viatris", "Sandoz", "Hikma", "Amneal", "Sun Pharmaceutical",
        "Dr. Reddy's Laboratories", "Cipla", "Aurobindo Pharma", "Zydus",
    )
)

# Products whose loss of exclusivity is a materially large generic opportunity.
BLOCKBUSTER_MARKERS: tuple[str, ...] = (
    "humira", "keytruda", "eliquis", "revlimid", "opdivo", "stelara", "imbruvica",
    "biktarvy", "trulicity", "ozempic", "jardiance", "entresto", "xarelto",
    "dolutegravir", "apixaban", "semaglutide", "tirzepatide", "dupixent",
    "skyrizi", "rinvoq", "veklury", "comirnaty", "prevnar", "gardasil",
)


@dataclass
class ScoreComponent:
    name: str
    raw: float  # 0..1
    weight: int
    reason: str

    @property
    def points(self) -> float:
        return self.raw * self.weight


@dataclass
class PriorityScore:
    total: int
    label: str
    components: list[ScoreComponent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "label": self.label,
            "components": [
                {
                    "name": c.name,
                    "raw": round(c.raw, 3),
                    "weight": c.weight,
                    "points": round(c.points, 2),
                    "reason": c.reason,
                }
                for c in self.components
            ],
        }


def label_for(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _recency_raw(when: date | datetime | None) -> tuple[float, str]:
    if when is None:
        return 0.4, "event date unknown"
    target = when.date() if isinstance(when, datetime) else when
    age = (date.today() - target).days
    if age <= 1:
        return 1.0, "detected today"
    if age <= 7:
        return 0.85, f"detected {age} days ago"
    if age <= 30:
        return 0.65, f"detected {age} days ago"
    if age <= 90:
        return 0.4, f"detected {age} days ago"
    return 0.2, "historical event"


def _patent_importance(patent: dict[str, Any] | None, drug_name: str | None) -> ScoreComponent:
    if not patent:
        raw, reason = 0.35, "no patent linkage available"
    else:
        raw = 0.4
        reasons = []
        if patent.get("drug_substance_flag"):
            raw += 0.2
            reasons.append("drug-substance patent")
        if patent.get("drug_product_flag"):
            raw += 0.1
            reasons.append("drug-product patent")
        if patent.get("patent_use_code"):
            raw += 0.1
            reasons.append(f"method-of-use {patent['patent_use_code']}")
        if patent.get("has_pte"):
            raw += 0.15
            reasons.append("term extended")
        if patent.get("delisted"):
            raw -= 0.2
            reasons.append("delisted")
        raw = max(0.0, min(1.0, raw))
        reason = ", ".join(reasons) or "listed patent"
    if drug_name and any(m in (drug_name or "").casefold() for m in BLOCKBUSTER_MARKERS):
        raw = min(1.0, raw + 0.25)
        reason += "; blockbuster product"
    return ScoreComponent("patent_importance", raw, WEIGHTS["patent_importance"], reason)


def _sponsor_importance(sponsor_name: str | None) -> ScoreComponent:
    if not sponsor_name:
        return ScoreComponent(
            "sponsor_importance", 0.4, WEIGHTS["sponsor_importance"], "sponsor not identified"
        )
    if normalize_name(sponsor_name) in MAJOR_SPONSORS:
        return ScoreComponent(
            "sponsor_importance", 1.0, WEIGHTS["sponsor_importance"], "major innovator sponsor"
        )
    return ScoreComponent(
        "sponsor_importance", 0.55, WEIGHTS["sponsor_importance"], "mid-size sponsor"
    )


def _revenue_potential(drug_name: str | None, therapy_area: str | None) -> ScoreComponent:
    raw = 0.5
    reason = "standard commercial profile"
    if drug_name and any(m in (drug_name or "").casefold() for m in BLOCKBUSTER_MARKERS):
        raw, reason = 1.0, "blockbuster-class product"
    elif therapy_area in {"Oncology", "Immunology", "Diabetes"}:
        raw, reason = 0.75, f"high-value therapy area ({therapy_area})"
    elif therapy_area in {"Rare disease", "Ophthalmology"}:
        raw, reason = 0.65, f"specialty therapy area ({therapy_area})"
    return ScoreComponent("revenue_potential", raw, WEIGHTS["revenue_potential"], reason)


def _market_competition(challenger_count: int | None) -> ScoreComponent:
    if challenger_count is None:
        return ScoreComponent(
            "market_competition", 0.45, WEIGHTS["market_competition"], "challenger count unknown"
        )
    if challenger_count >= 10:
        return ScoreComponent(
            "market_competition", 1.0, WEIGHTS["market_competition"], f"{challenger_count} ANDA filers"
        )
    if challenger_count >= 5:
        return ScoreComponent(
            "market_competition", 0.8, WEIGHTS["market_competition"], f"{challenger_count} ANDA filers"
        )
    if challenger_count >= 2:
        return ScoreComponent(
            "market_competition", 0.6, WEIGHTS["market_competition"], f"{challenger_count} ANDA filers"
        )
    return ScoreComponent(
        "market_competition", 0.35, WEIGHTS["market_competition"], "single challenger"
    )


def _exclusivity_impact(
    *,
    expiry: date | None,
    exclusivity_status: str | None,
    has_pte: bool,
) -> ScoreComponent:
    raw = 0.5
    reason = "baseline exclusivity position"
    if expiry is not None:
        days = (expiry - date.today()).days
        if days < 0:
            raw, reason = 0.85, "patent already expired — immediate generic entry"
        elif days <= 180:
            raw, reason = 1.0, f"patent expires in {days} days"
        elif days <= 365:
            raw, reason = 0.9, "patent expires within 12 months"
        elif days <= 730:
            raw, reason = 0.75, "patent expires within 24 months"
        elif days <= 1825:
            raw, reason = 0.55, "patent expires within 5 years"
        else:
            raw, reason = 0.3, "long remaining exclusivity"
    status = (exclusivity_status or "").casefold()
    if "eligible" in status:
        raw = min(1.0, raw + 0.1)
        reason += "; 180-day exclusivity eligible"
    elif "extinguished" in status:
        raw = min(1.0, raw + 0.15)
        reason += "; 180-day exclusivity extinguished"
    elif "deferred" in status:
        raw = min(1.0, raw + 0.05)
        reason += "; exclusivity deferred"
    if has_pte:
        raw = min(1.0, raw + 0.05)
        reason += "; PTE granted"
    return ScoreComponent("exclusivity_impact", raw, WEIGHTS["exclusivity_impact"], reason)


def compute_priority(
    *,
    patent: dict[str, Any] | None = None,
    sponsor_name: str | None = None,
    drug_name: str | None = None,
    therapy_area: str | None = None,
    challenger_count: int | None = None,
    expiry: date | None = None,
    exclusivity_status: str | None = None,
    has_pte: bool = False,
    occurred_at: date | datetime | None = None,
) -> PriorityScore:
    """Compute the weighted priority score and its explanation."""
    recency_raw, recency_reason = _recency_raw(occurred_at)
    components = [
        _patent_importance(patent, drug_name),
        _sponsor_importance(sponsor_name),
        _revenue_potential(drug_name, therapy_area),
        _market_competition(challenger_count),
        _exclusivity_impact(expiry=expiry, exclusivity_status=exclusivity_status, has_pte=has_pte),
        ScoreComponent("recency", recency_raw, WEIGHTS["recency"], recency_reason),
    ]
    total = int(round(sum(c.points for c in components)))
    total = max(0, min(100, total))
    return PriorityScore(total=total, label=label_for(total), components=components)
