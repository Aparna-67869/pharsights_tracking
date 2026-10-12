"""Module analytics: the aggregations powering each dashboard tab.

All functions are read-only and return plain dicts ready for JSON/GraphQL.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, desc, extract, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import (
    ActiveMoiety,
    Alert,
    DetectedChange,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    OrangeBookSupplement,
    Patent,
    PteApplication,
    PteCertificate,
)

log = get_logger(__name__)

_TODAY = date.today


# ---- FTF -------------------------------------------------------------------


def ftf_summary(session: Session) -> dict[str, Any]:
    base = select(func.count()).select_from(FtfRecord).where(FtfRecord.is_active.is_(True))
    total = session.scalar(base) or 0
    eligible = session.scalar(
        base.where(func.lower(FtfRecord.exclusivity_status) == "eligible")
    ) or 0
    extinguished = session.scalar(
        base.where(func.lower(FtfRecord.exclusivity_status) == "extinguished")
    ) or 0
    deferred = session.scalar(
        base.where(func.lower(FtfRecord.exclusivity_status) == "deferred")
    ) or 0
    cutoff = _TODAY() - timedelta(days=365)
    recent = session.scalar(
        base.where(FtfRecord.date_of_submission >= cutoff)
    ) or 0
    expiring_soon = session.scalar(
        base.where(
            FtfRecord.last_qualifying_patent_expiry.is_not(None),
            FtfRecord.last_qualifying_patent_expiry <= _TODAY() + timedelta(days=730),
            FtfRecord.last_qualifying_patent_expiry >= _TODAY(),
        )
    ) or 0
    return {
        "total_filings": total,
        "eligible_180_day": eligible,
        "extinguished_180_day": extinguished,
        "deferred": deferred,
        "filings_last_12_months": recent,
        "patents_expiring_24_months": expiring_soon,
    }


def ftf_monthly_trend(session: Session, months: int = 36) -> list[dict[str, Any]]:
    cutoff = _TODAY() - timedelta(days=months * 31)
    rows = session.execute(
        select(
            extract("year", FtfRecord.date_of_submission).label("year"),
            extract("month", FtfRecord.date_of_submission).label("month"),
            func.count(FtfRecord.id),
        )
        .where(
            FtfRecord.is_active.is_(True),
            FtfRecord.date_of_submission.is_not(None),
            FtfRecord.date_of_submission >= cutoff,
        )
        .group_by("year", "month")
        .order_by("year", "month")
    ).all()
    return [
        {"period": f"{int(r[0])}-{int(r[1]):02d}", "year": int(r[0]), "month": int(r[1]), "count": r[2]}
        for r in rows
    ]


def ftf_top_therapy_areas(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Drug.therapy_area, func.count(FtfRecord.id))
        .join(Drug, FtfRecord.drug_id == Drug.id)
        .where(FtfRecord.is_active.is_(True), Drug.therapy_area.is_not(None))
        .group_by(Drug.therapy_area)
        .order_by(desc(func.count(FtfRecord.id)))
        .limit(limit)
    ).all()
    return [{"therapy_area": r[0], "count": r[1]} for r in rows]


# ---- PTE -------------------------------------------------------------------


def pte_summary(session: Session) -> dict[str, Any]:
    app_total = session.scalar(
        select(func.count()).select_from(PteApplication).where(PteApplication.is_active.is_(True))
    ) or 0
    cert_total = session.scalar(
        select(func.count()).select_from(PteCertificate).where(PteCertificate.is_active.is_(True))
    ) or 0
    cutoff = _TODAY() - timedelta(days=365)
    new_apps = session.scalar(
        select(func.count())
        .select_from(PteApplication)
        .where(PteApplication.is_active.is_(True), PteApplication.filing_date >= cutoff)
    ) or 0
    new_certs = session.scalar(
        select(func.count())
        .select_from(PteCertificate)
        .where(PteCertificate.is_active.is_(True), PteCertificate.granted_date >= cutoff)
    ) or 0
    avg_days = session.scalar(
        select(func.avg(PteCertificate.extension_days)).where(
            PteCertificate.is_active.is_(True), PteCertificate.extension_days.is_not(None)
        )
    )
    return {
        "applications_total": app_total,
        "certificates_total": cert_total,
        "applications_last_12_months": new_apps,
        "certificates_last_12_months": new_certs,
        "average_extension_days": round(float(avg_days), 1) if avg_days else None,
    }


def pte_monthly_trend(session: Session, months: int = 60) -> list[dict[str, Any]]:
    cutoff = _TODAY() - timedelta(days=months * 31)
    rows = session.execute(
        select(
            extract("year", PteApplication.filing_date).label("year"),
            extract("month", PteApplication.filing_date).label("month"),
            func.count(PteApplication.id),
        )
        .where(
            PteApplication.is_active.is_(True),
            PteApplication.filing_date.is_not(None),
            PteApplication.filing_date >= cutoff,
        )
        .group_by("year", "month")
        .order_by("year", "month")
    ).all()
    return [
        {"period": f"{int(r[0])}-{int(r[1]):02d}", "year": int(r[0]), "month": int(r[1]), "count": r[2]}
        for r in rows
    ]


def pte_extension_distribution(session: Session) -> list[dict[str, Any]]:
    """Bucket granted extensions into the statutory bands."""
    rows = session.execute(
        select(PteCertificate.extension_days).where(
            PteCertificate.is_active.is_(True), PteCertificate.extension_days.is_not(None)
        )
    ).all()
    buckets = {"<1 year": 0, "1-2 years": 0, "2-3 years": 0, "3-5 years": 0, ">5 years": 0}
    for (days,) in rows:
        years = (days or 0) / 365.0
        if years < 1:
            buckets["<1 year"] += 1
        elif years < 2:
            buckets["1-2 years"] += 1
        elif years < 3:
            buckets["2-3 years"] += 1
        elif years <= 5:
            buckets["3-5 years"] += 1
        else:
            buckets[">5 years"] += 1
    return [{"band": k, "count": v} for k, v in buckets.items()]


# ---- PDE -------------------------------------------------------------------


def pde_summary(session: Session) -> dict[str, Any]:
    total = session.scalar(
        select(func.count()).select_from(ActiveMoiety).where(ActiveMoiety.is_active.is_(True))
    ) or 0
    cutoff = _TODAY() - timedelta(days=365)
    recent = session.scalar(
        select(func.count())
        .select_from(ActiveMoiety)
        .where(ActiveMoiety.is_active.is_(True), ActiveMoiety.date_issued >= cutoff)
    ) or 0
    sponsors = session.scalar(
        select(func.count(func.distinct(ActiveMoiety.sponsor_name))).where(
            ActiveMoiety.is_active.is_(True), ActiveMoiety.sponsor_name.is_not(None)
        )
    ) or 0
    return {
        "total_moieties": total,
        "approved_last_12_months": recent,
        "distinct_sponsors": sponsors,
    }


def pde_yearly_trend(session: Session, years: int = 15) -> list[dict[str, Any]]:
    cutoff_year = _TODAY().year - years
    rows = session.execute(
        select(ActiveMoiety.approval_year, func.count(ActiveMoiety.id))
        .where(
            ActiveMoiety.is_active.is_(True),
            ActiveMoiety.approval_year.is_not(None),
            ActiveMoiety.approval_year >= cutoff_year,
        )
        .group_by(ActiveMoiety.approval_year)
        .order_by(ActiveMoiety.approval_year)
    ).all()
    return [{"year": int(r[0]), "count": r[1]} for r in rows]


def pde_top_sponsors(session: Session, limit: int = 15) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ActiveMoiety.sponsor_name, func.count(ActiveMoiety.id))
        .where(ActiveMoiety.is_active.is_(True), ActiveMoiety.sponsor_name.is_not(None))
        .group_by(ActiveMoiety.sponsor_name)
        .order_by(desc(func.count(ActiveMoiety.id)))
        .limit(limit)
    ).all()
    return [{"sponsor": r[0], "count": r[1]} for r in rows]


# ---- Orange Book -----------------------------------------------------------


def orange_book_summary(session: Session) -> dict[str, Any]:
    products = session.scalar(
        select(func.count()).select_from(OrangeBookProduct).where(OrangeBookProduct.is_active.is_(True))
    ) or 0
    nda = session.scalar(
        select(func.count())
        .select_from(OrangeBookProduct)
        .where(OrangeBookProduct.is_active.is_(True), OrangeBookProduct.appl_type == "N")
    ) or 0
    anda = session.scalar(
        select(func.count())
        .select_from(OrangeBookProduct)
        .where(OrangeBookProduct.is_active.is_(True), OrangeBookProduct.appl_type == "A")
    ) or 0
    patents = session.scalar(
        select(func.count()).select_from(OrangeBookPatent).where(OrangeBookPatent.is_active.is_(True))
    ) or 0
    exclusivity = session.scalar(
        select(func.count())
        .select_from(OrangeBookExclusivity)
        .where(OrangeBookExclusivity.is_active.is_(True))
    ) or 0
    current = session.scalars(
        select(OrangeBookSupplement).where(OrangeBookSupplement.is_current.is_(True)).limit(1)
    ).first()
    return {
        "total_products": products,
        "nda_products": nda,
        "anda_products": anda,
        "patent_listings": patents,
        "exclusivity_grants": exclusivity,
        "current_supplement": {
            "number": current.supplement_number if current else None,
            "edition": current.edition if current else None,
            "publication_month": current.publication_month if current else None,
            "publication_year": current.publication_year if current else None,
        }
        if current
        else None,
    }


def orange_book_supplement_history(session: Session, limit: int = 24) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(OrangeBookSupplement)
        .order_by(desc(OrangeBookSupplement.publication_year), desc(OrangeBookSupplement.publication_month))
        .limit(limit)
    )
    return [
        {
            "supplement_number": r.supplement_number,
            "edition": r.edition,
            "publication_month": r.publication_month,
            "publication_year": r.publication_year,
            "products_added": r.products_added,
            "products_removed": r.products_removed,
            "products_modified": r.products_modified,
            "is_current": r.is_current,
        }
        for r in rows
    ]


# ---- Patents ---------------------------------------------------------------


def patent_expiry_timeline(session: Session, years: int = 10) -> list[dict[str, Any]]:
    """Count patents (deduplicated) by expiry year for the next ``years``."""
    today = _TODAY()
    end = today + timedelta(days=years * 366)
    rows = session.execute(
        select(
            extract("year", Patent.expiration_date).label("year"),
            func.count(Patent.id),
        )
        .where(
            Patent.expiration_date.is_not(None),
            Patent.expiration_date >= today,
            Patent.expiration_date <= end,
        )
        .group_by("year")
        .order_by("year")
    ).all()
    return [{"year": int(r[0]), "count": r[1]} for r in rows]


def patents_expiring_soon(session: Session, months: int = 24, limit: int = 100) -> list[dict[str, Any]]:
    today = _TODAY()
    end = today + timedelta(days=months * 31)
    rows = session.scalars(
        select(Patent)
        .where(Patent.expiration_date >= today, Patent.expiration_date <= end)
        .order_by(Patent.expiration_date)
        .limit(limit)
    )
    return [
        {
            "patent_number": p.patent_number,
            "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
            "has_pte": p.has_pte,
            "has_paragraph_iv": p.has_paragraph_iv,
            "assignee": p.assignee,
            "days_remaining": (p.expiration_date - today).days if p.expiration_date else None,
        }
        for p in rows
    ]


def sponsor_leaderboard(session: Session, limit: int = 15) -> list[dict[str, Any]]:
    """Rank sponsors by total monitored activity across every module."""
    results: dict[str, dict[str, Any]] = {}

    def _bump(name: str | None, key: str) -> None:
        if not name:
            return
        entry = results.setdefault(name, {"sponsor": name, "nda": 0, "pde": 0, "pte": 0, "ftf": 0, "total": 0})
        entry[key] += 1
        entry["total"] += 1

    for (name,) in session.execute(
        select(OrangeBookProduct.applicant_full_name)
        .where(OrangeBookProduct.is_active.is_(True), OrangeBookProduct.appl_type == "N")
    ).all():
        _bump(name, "nda")
    for (name,) in session.execute(
        select(ActiveMoiety.sponsor_name).where(ActiveMoiety.is_active.is_(True))
    ).all():
        _bump(name, "pde")
    for (name,) in session.execute(
        select(PteCertificate.sponsor_name).where(
            PteCertificate.is_active.is_(True), PteCertificate.sponsor_name.is_not(None)
        )
    ).all():
        _bump(name, "pte")

    ranked = sorted(results.values(), key=lambda r: r["total"], reverse=True)[:limit]
    return ranked


def therapy_area_analysis(session: Session) -> list[dict[str, Any]]:
    """Drug counts, patent exposure and FTF activity per therapy area."""
    area_drugs = dict(
        session.execute(
            select(Drug.therapy_area, func.count(Drug.id))
            .where(Drug.therapy_area.is_not(None))
            .group_by(Drug.therapy_area)
        ).all()
    )
    ftf_by_area = dict(
        session.execute(
            select(Drug.therapy_area, func.count(FtfRecord.id))
            .join(FtfRecord, FtfRecord.drug_id == Drug.id)
            .where(FtfRecord.is_active.is_(True), Drug.therapy_area.is_not(None))
            .group_by(Drug.therapy_area)
        ).all()
    )
    result = []
    for area, count in area_drugs.items():
        result.append(
            {
                "therapy_area": area,
                "drugs": count,
                "ftf_filings": ftf_by_area.get(area, 0),
            }
        )
    return sorted(result, key=lambda r: r["drugs"], reverse=True)


# ---- Cross-module ----------------------------------------------------------


def executive_kpis(session: Session) -> dict[str, Any]:
    """The executive dashboard KPI strip."""
    today = _TODAY()
    cutoff_30 = today - timedelta(days=30)

    def _count(model, *conditions) -> int:
        stmt = select(func.count()).select_from(model)
        for condition in conditions:
            stmt = stmt.where(condition)
        return session.scalar(stmt) or 0

    open_alerts = _count(Alert, Alert.status == "open")
    high_risk = _count(
        Alert, Alert.status == "open", Alert.priority_label.in_(["critical", "high"])
    )
    # Activity KPIs use the regulatory date carried by the source (the true event
    # date), not the ingestion timestamp — otherwise the first load of a source
    # would report every historical record as "new this month".
    new_ftf = _count(
        FtfRecord, FtfRecord.is_active.is_(True), FtfRecord.date_of_submission >= cutoff_30
    )
    new_pte_apps = _count(
        PteApplication, PteApplication.is_active.is_(True), PteApplication.filing_date >= cutoff_30
    )
    new_pte_certs = _count(
        PteCertificate, PteCertificate.is_active.is_(True), PteCertificate.granted_date >= cutoff_30
    )
    new_moieties = _count(
        ActiveMoiety, ActiveMoiety.is_active.is_(True), ActiveMoiety.date_issued >= cutoff_30
    )
    # Orange Book rows carry no reliable per-record event date, so this KPI counts
    # genuinely detected (non-baseline) changes instead.
    ob_updates = _count(
        DetectedChange,
        DetectedChange.module == "orange_book",
        DetectedChange.detected_at >= cutoff_30,
        DetectedChange.is_baseline.is_(False),
    )
    drugs_monitored = _count(Drug)
    patents_expiring = _count(
        Patent,
        Patent.expiration_date.is_not(None),
        Patent.expiration_date >= today,
        Patent.expiration_date <= today + timedelta(days=730),
    )
    changes_30d = _count(
        DetectedChange,
        DetectedChange.detected_at >= cutoff_30,
        DetectedChange.is_baseline.is_(False),
    )

    return {
        "drugs_monitored": drugs_monitored,
        "patents_expiring_soon": patents_expiring,
        "new_ftf_records": new_ftf,
        "new_pte_applications": new_pte_apps,
        "new_pte_grants": new_pte_certs,
        "new_active_moieties": new_moieties,
        "orange_book_updates": ob_updates,
        "open_alerts": open_alerts,
        "high_risk_opportunities": high_risk,
        "changes_last_30_days": changes_30d,
        "insights_total": _count(Insight),
    }


def generic_opportunity_heatmap(session: Session, limit: int = 25) -> list[dict[str, Any]]:
    """Products ranked by generic-entry attractiveness (near-term patent expiry)."""
    today = _TODAY()
    horizon = today + timedelta(days=1095)  # 3 years
    rows = session.execute(
        select(
            OrangeBookProduct.trade_name,
            OrangeBookProduct.ingredient,
            OrangeBookProduct.applicant_full_name,
            OrangeBookProduct.appl_type,
            OrangeBookProduct.appl_no,
            func.min(OrangeBookPatent.expiration_date),
            func.count(OrangeBookPatent.id),
        )
        .join(
            OrangeBookPatent,
            and_(
                OrangeBookPatent.appl_no == OrangeBookProduct.appl_no,
                OrangeBookPatent.appl_type == OrangeBookProduct.appl_type,
            ),
        )
        .where(
            OrangeBookProduct.is_active.is_(True),
            OrangeBookPatent.is_active.is_(True),
            OrangeBookPatent.expiration_date.is_not(None),
            OrangeBookPatent.expiration_date <= horizon,
        )
        .group_by(
            OrangeBookProduct.trade_name,
            OrangeBookProduct.ingredient,
            OrangeBookProduct.applicant_full_name,
            OrangeBookProduct.appl_type,
            OrangeBookProduct.appl_no,
        )
        .order_by(func.min(OrangeBookPatent.expiration_date))
        .limit(limit)
    ).all()

    heatmap = []
    for trade, ingredient, applicant, appl_type, appl_no, expiry, patent_count in rows:
        days = (expiry - today).days if expiry else None
        if days is None:
            intensity = 0.2
        elif days <= 180:
            intensity = 1.0
        elif days <= 365:
            intensity = 0.85
        elif days <= 730:
            intensity = 0.65
        else:
            intensity = 0.45
        heatmap.append(
            {
                "product": trade or ingredient,
                "ingredient": ingredient,
                "applicant": applicant,
                "application": f"{appl_type}{appl_no}",
                "nearest_patent_expiry": expiry.isoformat() if expiry else None,
                "days_to_expiry": days,
                "listed_patents": patent_count,
                "opportunity_score": round(intensity * 100),
            }
        )
    return heatmap


def patent_family_distribution(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Patents grouped by assignee, for the family-distribution chart."""
    rows = session.execute(
        select(Patent.assignee, func.count(Patent.id))
        .where(Patent.assignee.is_not(None))
        .group_by(Patent.assignee)
        .order_by(desc(func.count(Patent.id)))
        .limit(limit)
    ).all()
    return [{"assignee": r[0], "patents": r[1]} for r in rows]


def monthly_fda_activity(session: Session, months: int = 24) -> list[dict[str, Any]]:
    """Combined FDA activity per month across FTF, PTE, PDE and Orange Book."""
    cutoff = _TODAY() - timedelta(days=months * 31)

    def _series(model, column) -> dict[str, int]:
        rows = session.execute(
            select(
                extract("year", column).label("year"),
                extract("month", column).label("month"),
                func.count(model.id),
            )
            .where(model.is_active.is_(True), column.is_not(None), column >= cutoff)
            .group_by("year", "month")
        ).all()
        return {f"{int(r[0])}-{int(r[1]):02d}": r[2] for r in rows}

    ftf = _series(FtfRecord, FtfRecord.date_of_submission)
    pte = _series(PteApplication, PteApplication.filing_date)
    pde = _series(ActiveMoiety, ActiveMoiety.date_issued)
    ob = _series(OrangeBookProduct, OrangeBookProduct.approval_date)

    periods = sorted(set(ftf) | set(pte) | set(pde) | set(ob))
    return [
        {
            "period": period,
            "ftf": ftf.get(period, 0),
            "pte": pte.get(period, 0),
            "pde": pde.get(period, 0),
            "orange_book": ob.get(period, 0),
            "total": ftf.get(period, 0) + pte.get(period, 0) + pde.get(period, 0) + ob.get(period, 0),
        }
        for period in periods
    ]
