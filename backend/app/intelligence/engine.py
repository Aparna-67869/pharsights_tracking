"""AI Impact Analysis Engine.

Turns a ``DetectedChange`` into an actionable ``Insight`` answering the SOP's
eight questions:

  1. What changed?               -> ``what_changed``
  2. Why does it matter?         -> ``why_it_matters``
  3. Which company is affected?  -> ``affected_companies``
  4. What products are impacted? -> ``affected_products``
  5. Generic opportunity?        -> ``generic_opportunity``
  6. Exclusivity risk?           -> ``exclusivity_risk``
  7. Recommended action?         -> ``recommended_action``
  8. Priority level?             -> ``priority_score`` / ``priority_label``

The narrative is generated deterministically from the change payload plus
knowledge-graph context, so it works with no LLM configured. When an LLM is
available, :mod:`app.copilot.llm` enriches the text; the structured fields and
the score never depend on the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.text import clean_text
from app.db.models import (
    DetectedChange,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookProduct,
    Patent,
    PteCertificate,
    Sponsor,
)
from app.intelligence.priority import compute_priority

log = get_logger(__name__)

FIELD_LABELS = {
    "drug_name": "Drug name",
    "dosage_form": "Dosage form",
    "strength": "Strength",
    "rld_brand_name": "RLD brand",
    "nda_number": "NDA number",
    "date_of_submission": "Paragraph IV submission date",
    "number_of_andas": "Number of ANDAs submitted",
    "exclusivity_status": "180-day exclusivity status",
    "decision_posting_date": "180-day decision posting date",
    "first_applicant_approval_date": "First applicant approval date",
    "first_commercial_marketing_date": "First commercial marketing date",
    "last_qualifying_patent_expiry": "Last qualifying patent expiry",
    "patent_number": "Patent number",
    "filing_date": "PTE filing date",
    "trade_name": "Trade name",
    "generic_name": "Generic name",
    "original_expiration_date": "Original patent expiry",
    "extension_days": "Extension granted (days)",
    "extension_text": "Extension granted",
    "moiety_name": "Active moiety",
    "sponsor_name": "Sponsor",
    "date_issued": "Date issued",
    "ingredient": "Ingredient",
    "applicant": "Applicant",
    "approval_date": "Approval date",
    "te_code": "Therapeutic equivalence code",
    "expiration_date": "Patent expiry",
    "exclusivity_code": "Exclusivity code",
    "exclusivity_date": "Exclusivity date",
    "rld": "Reference listed drug",
    "rs": "Reference standard",
}


@dataclass
class ImpactContext:
    """Everything the engine needs to reason about one change."""

    change: DetectedChange
    drug: Drug | None = None
    patent: Patent | None = None
    sponsor: Sponsor | None = None
    ftf: FtfRecord | None = None
    pte_certificate: PteCertificate | None = None
    challenger_count: int | None = None
    related_products: list[str] | None = None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _humanize_field_changes(changes: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for change in changes:
        field = FIELD_LABELS.get(change.get("field"), change.get("field", "field"))
        before = change.get("before")
        after = change.get("after")
        if before in (None, "") and after not in (None, ""):
            lines.append(f"{field} added: {after}")
        elif after in (None, "") and before not in (None, ""):
            lines.append(f"{field} cleared (was {before})")
        else:
            lines.append(f"{field} changed from {before} to {after}")
    return lines


# ---- Context loading -------------------------------------------------------


def load_context(session: Session, change: DetectedChange) -> ImpactContext:
    context = ImpactContext(change=change)
    after = change.after or {}
    before = change.before or {}
    payload = after or before

    if change.entity_type == "ftf_record":
        row = session.scalars(
            select(FtfRecord)
            .where(FtfRecord.source_key == change.source_key, FtfRecord.is_active.is_(True))
            .limit(1)
        ).first()
        context.ftf = row
        if row is not None:
            context.drug = session.get(Drug, row.drug_id) if row.drug_id else None
            context.patent = session.get(Patent, row.patent_id) if row.patent_id else None
            context.sponsor = session.get(Sponsor, row.sponsor_id) if row.sponsor_id else None
            context.challenger_count = row.number_of_andas
            if row.drug_id:
                context.challenger_count = (
                    row.number_of_andas
                    or session.scalar(
                        select(FtfRecord.number_of_andas)
                        .where(FtfRecord.drug_id == row.drug_id, FtfRecord.is_active.is_(True))
                        .limit(1)
                    )
                )

    elif change.entity_type == "pte_application":
        patent_number = payload.get("patent_number")
        if patent_number:
            context.patent = session.scalars(
                select(Patent).where(Patent.normalized_number == str(patent_number).upper())
            ).first()
        trade = payload.get("trade_name")
        if trade:
            context.drug = session.scalars(
                select(Drug).where(Drug.name == trade).limit(1)
            ).first()

    elif change.entity_type == "pte_certificate":
        row = session.scalars(
            select(PteCertificate)
            .where(PteCertificate.source_key == change.source_key, PteCertificate.is_active.is_(True))
            .limit(1)
        ).first()
        context.pte_certificate = row
        if row is not None:
            context.patent = session.get(Patent, row.patent_id) if row.patent_id else None
            context.drug = session.get(Drug, row.drug_id) if row.drug_id else None
            context.sponsor = session.get(Sponsor, row.sponsor_id) if row.sponsor_id else None

    elif change.entity_type == "active_moiety":
        name = payload.get("moiety_name")
        sponsor_name = payload.get("sponsor_name")
        if name:
            context.drug = session.scalars(
                select(Drug).where(Drug.normalized_name == str(name).casefold()).limit(1)
            ).first()
        if sponsor_name:
            context.sponsor = session.scalars(
                select(Sponsor).where(Sponsor.name == sponsor_name).limit(1)
            ).first()

    elif change.entity_type in {"orange_book_product", "orange_book_patent", "orange_book_exclusivity"}:
        appl_no = payload.get("appl_no")
        if appl_no:
            product = session.scalars(
                select(OrangeBookProduct)
                .where(
                    OrangeBookProduct.appl_no == str(appl_no),
                    OrangeBookProduct.is_active.is_(True),
                )
                .limit(1)
            ).first()
            if product is not None:
                context.drug = session.get(Drug, product.drug_id) if product.drug_id else None
                context.sponsor = session.get(Sponsor, product.sponsor_id) if product.sponsor_id else None
                context.related_products = [product.trade_name or product.ingredient or ""]
        patent_number = payload.get("patent_number")
        if patent_number:
            context.patent = session.scalars(
                select(Patent).where(Patent.normalized_number == str(patent_number).upper())
            ).first()

    return context


# ---- Narrative generation --------------------------------------------------


def _what_changed(context: ImpactContext) -> str:
    change = context.change
    entity = change.entity_type.replace("_", " ")
    if change.change_type == "added":
        prefix = f"New {entity} detected"
    elif change.change_type == "removed":
        prefix = f"{entity.title()} withdrawn from the source list"
    else:
        prefix = f"{entity.title()} updated"
    details = _humanize_field_changes(change.field_changes)
    if details:
        return f"{prefix}: " + "; ".join(details[:6]) + "."
    after = change.after or {}
    label = (
        after.get("drug_name")
        or after.get("trade_name")
        or after.get("moiety_name")
        or after.get("patent_number")
        or change.source_key
    )
    return f"{prefix}: {label}."


def _why_it_matters(context: ImpactContext) -> str:
    change = context.change
    parts: list[str] = []
    if change.entity_type == "ftf_record":
        parts.append(
            "A Paragraph IV certification is a formal patent challenge by a generic "
            "applicant. It is the earliest observable signal of generic entry and it "
            "starts the 180-day first-to-file exclusivity clock."
        )
        if change.change_type == "added":
            parts.append("A newly listed certification indicates a fresh challenge to this product.")
    elif change.entity_type == "pte_application":
        parts.append(
            "A patent term extension application extends market exclusivity beyond the "
            "original patent expiry, delaying generic entry if granted."
        )
    elif change.entity_type == "pte_certificate":
        parts.append(
            "A granted PTE certificate adds up to five years of exclusivity to the patent, "
            "directly shifting the generic entry date."
        )
    elif change.entity_type == "active_moiety":
        parts.append(
            "An approved active moiety record marks a product with no previously approved "
            "active moiety, which qualifies for five-year new chemical entity exclusivity."
        )
    elif change.entity_type == "orange_book_product":
        parts.append(
            "Orange Book listings define the reference product and the patents that a "
            "generic applicant must certify against."
        )
    elif change.entity_type == "orange_book_patent":
        parts.append(
            "Patent listings in the Orange Book are the patents a generic applicant must "
            "address in its ANDA; changes here alter the certification landscape."
        )
    elif change.entity_type == "orange_book_exclusivity":
        parts.append(
            "Exclusivity grants block approval of competing generics for their duration."
        )

    expiry = None
    if context.patent is not None:
        expiry = context.patent.expiration_date
    elif context.ftf is not None:
        expiry = context.ftf.last_qualifying_patent_expiry
    if expiry:
        days = (expiry - date.today()).days
        if days > 0:
            parts.append(f"Nearest relevant patent expiry is {expiry.isoformat()} ({days} days away).")
        else:
            parts.append(f"Nearest relevant patent expired on {expiry.isoformat()}.")
    return " ".join(parts)


def _affected_companies(context: ImpactContext) -> list[str]:
    companies: list[str] = []
    if context.sponsor is not None and context.sponsor.name:
        companies.append(context.sponsor.name)
    # A removed row has no `after`; fall back to the last known state so the
    # affected parties are still reported.
    payload = context.change.after or context.change.before or {}
    for key in ("applicant", "sponsor_name", "applicant_full_name", "rld_brand_name"):
        value = clean_text(payload.get(key))
        if value and value not in companies:
            companies.append(value)
    return companies


def _affected_products(context: ImpactContext) -> list[str]:
    products: list[str] = []
    payload = context.change.after or context.change.before or {}
    for key in ("drug_name", "trade_name", "moiety_name", "ingredient"):
        value = clean_text(payload.get(key))
        if value and value not in products:
            products.append(value)
    if context.drug is not None and context.drug.name not in products:
        products.append(context.drug.name)
    if context.related_products:
        for item in context.related_products:
            if item and item not in products:
                products.append(item)
    return products[:8]


def _generic_opportunity(context: ImpactContext) -> str | None:
    change = context.change
    expiry = None
    if context.patent is not None:
        expiry = context.patent.expiration_date
    elif context.ftf is not None:
        expiry = context.ftf.last_qualifying_patent_expiry

    if change.entity_type == "ftf_record" and change.change_type == "added":
        return (
            "Yes — a new Paragraph IV filing confirms at least one generic applicant "
            "believes the listed patents are invalid, unenforceable or not infringed. "
            "Generic entry is credible; monitor the 30-month stay and litigation outcome."
        )
    if change.entity_type == "orange_book_product" and change.change_type == "removed":
        return (
            "Possible — the product left the Orange Book listing. Verify discontinuation "
            "versus a data correction before treating this as an opportunity."
        )
    if expiry is not None:
        days = (expiry - date.today()).days
        if days <= 0:
            return "Yes — no patent barrier remains; generic entry can proceed subject to exclusivity."
        if days <= 730:
            return f"Emerging — patent expiry in {days} days makes this a near-term opportunity."
    if change.entity_type == "orange_book_exclusivity":
        return "Indirect — exclusivity changes shift the entry date for already-filed generics."
    return None


def _exclusivity_risk(context: ImpactContext) -> str | None:
    change = context.change
    if change.entity_type == "pte_certificate":
        days = None
        if context.pte_certificate is not None:
            days = context.pte_certificate.extension_days
        return (
            "Elevated — a PTE certificate extends exclusivity"
            + (f" by approximately {days} days" if days else "")
            + ", pushing the earliest generic entry date out."
        )
    if change.entity_type == "pte_application":
        return "Watch — if granted, the extension will delay generic entry beyond the current expiry."
    if change.entity_type == "orange_book_exclusivity":
        code = (change.after or {}).get("exclusivity_code")
        return f"Active exclusivity {code} blocks competing approvals until its expiry date."
    if context.ftf is not None and (context.ftf.exclusivity_status or "").casefold() == "eligible":
        return "First-filer 180-day exclusivity is available; a successful first filer can block others."
    if context.ftf is not None and (context.ftf.exclusivity_status or "").casefold() == "extinguished":
        return "180-day exclusivity was extinguished — multiple generics may enter simultaneously."
    return None


def _recommended_action(context: ImpactContext) -> str:
    change = context.change
    entity = change.entity_type
    if entity == "ftf_record" and change.change_type == "added":
        return (
            "Review the patent family and any litigation history immediately. Confirm whether "
            "a 30-month stay applies, check for a first-filer 180-day exclusivity claim, and "
            "update the product's generic-entry forecast."
        )
    if entity == "ftf_record" and change.change_type == "removed":
        return (
            "Confirm whether the withdrawal reflects a settlement, a patent delisting or a data "
            "correction. Re-run the entry forecast for this product."
        )
    if entity == "ftf_record" and change.change_type == "updated":
        fields = {c.get("field") for c in change.field_changes}
        if "exclusivity_status" in fields:
            return (
                "Re-assess the 180-day exclusivity position for this product. A change in status "
                "alters who can launch first and when competing generics may enter."
            )
        if "number_of_andas" in fields:
            return (
                "Update the competitive intensity model for this product: the number of ANDA "
                "filers has changed, which affects pricing at entry."
            )
        if "last_qualifying_patent_expiry" in fields:
            return (
                "Refresh the patent expiry used in the entry forecast and confirm the change "
                "against the source document."
            )
        return (
            "Compare the updated record against the previous version, confirm the change against "
            "the source document, and refresh the product's generic-entry forecast."
        )
    if entity == "pte_application":
        return (
            "Track the application through examination. Model the extension in the exclusivity "
            "timeline and flag the affected patent for IP counsel review."
        )
    if entity == "pte_certificate":
        return (
            "Update the patent expiry in the exclusivity model and notify IP counsel. Recalculate "
            "the generic entry date for every product covered by this patent."
        )
    if entity == "active_moiety" and change.change_type == "added":
        return (
            "Record the five-year NCE exclusivity start date and add the product to the "
            "competitive watchlist for its therapy area."
        )
    if entity == "orange_book_product" and change.change_type == "added":
        return "Validate the new listing, capture its patents and exclusivity, and update the product map."
    if entity == "orange_book_product" and change.change_type == "removed":
        return "Verify the removal against the source PDF and determine whether a generic entry occurred."
    if entity == "orange_book_patent":
        return (
            "Compare the patent listing against the prior version. Confirm the use code and "
            "expiry, then refresh the certification landscape for the product."
        )
    if entity == "orange_book_exclusivity":
        return "Update the exclusivity calendar and re-forecast generic entry for the affected application."
    return "Review the change, confirm it against the source document, and update the product record."


# ---- Engine ----------------------------------------------------------------


def analyze_change(session: Session, change: DetectedChange) -> Insight:
    """Generate (and persist) the insight for one detected change."""
    context = load_context(session, change)
    payload = change.after or change.before or {}

    patent_dict: dict[str, Any] | None = None
    if context.patent is not None:
        patent_dict = {
            "drug_substance_flag": context.patent.drug_substance_flag,
            "drug_product_flag": context.patent.drug_product_flag,
            "patent_use_code": context.patent.patent_use_code,
            "has_pte": context.patent.has_pte,
            "delisted": context.patent.delisted,
        }

    drug_name = (
        (context.drug.name if context.drug else None)
        or payload.get("drug_name")
        or payload.get("trade_name")
        or payload.get("ingredient")
    )
    # Include the RLD brand name when judging commercial weight: the FTF list
    # names the brand the challenger is targeting, which is what identifies a
    # blockbuster (e.g. the challenger is "Pembrolizumab", the brand is "Keytruda").
    scoring_name = (
        " ".join(
            part
            for part in (drug_name, payload.get("rld_brand_name"), payload.get("trade_name"))
            if part
        )
        or None
    )
    therapy_area = context.drug.therapy_area if context.drug else None
    sponsor_name = (
        (context.sponsor.name if context.sponsor else None)
        or payload.get("sponsor_name")
        or payload.get("applicant")
    )
    expiry = None
    if context.patent is not None:
        expiry = context.patent.expiration_date
    if expiry is None and context.ftf is not None:
        expiry = context.ftf.last_qualifying_patent_expiry
    if expiry is None:
        expiry = _as_date(payload.get("expiration_date") or payload.get("last_qualifying_patent_expiry"))

    exclusivity_status = payload.get("exclusivity_status")
    if exclusivity_status is None and context.ftf is not None:
        exclusivity_status = context.ftf.exclusivity_status
    has_pte = bool(context.patent.has_pte) if context.patent else False

    score = compute_priority(
        patent=patent_dict,
        sponsor_name=sponsor_name,
        drug_name=scoring_name,
        therapy_area=therapy_area,
        challenger_count=context.challenger_count,
        expiry=expiry,
        exclusivity_status=exclusivity_status,
        has_pte=has_pte,
        occurred_at=change.detected_at,
    )

    title_subject = drug_name or payload.get("moiety_name") or payload.get("patent_number") or change.source_key
    title = f"{change.change_type.title()}: {change.entity_type.replace('_', ' ')} — {title_subject}"

    insight = Insight(
        change_id=change.id,
        module=change.module,
        entity_type=change.entity_type,
        entity_key=change.source_key,
        title=title[:512],
        what_changed=_what_changed(context),
        why_it_matters=_why_it_matters(context),
        affected_companies=_affected_companies(context),
        affected_products=_affected_products(context),
        generic_opportunity=_generic_opportunity(context),
        exclusivity_risk=_exclusivity_risk(context),
        recommended_action=_recommended_action(context),
        priority_score=score.total,
        priority_label=score.label,
        score_breakdown=score.to_dict(),
        evidence=[
            {
                "source_code": change.source_code,
                "document_id": change.document_id,
                "detected_at": change.detected_at.isoformat() if change.detected_at else None,
                "field_changes": change.field_changes,
            }
        ],
        generated_by="rule_engine",
        confidence=0.85,
    )
    session.add(insight)
    session.flush()

    change.processed = True
    session.flush()
    return insight


def analyze_pending_changes(session: Session, *, limit: int = 500, include_baseline: bool = False) -> list[Insight]:
    """Analyze every unprocessed change and return the generated insights.

    Baseline changes (the first snapshot of a source) are marked processed
    without producing insights, so a new source does not generate a burst of
    noise. Their history is still fully queryable via the change log.
    """
    query = select(DetectedChange).where(DetectedChange.processed.is_(False))
    if not include_baseline:
        query = query.where(DetectedChange.is_baseline.is_(False))
    changes = list(
        session.scalars(query.order_by(DetectedChange.detected_at.desc()).limit(limit))
    )

    baseline_ids = list(
        session.scalars(
            select(DetectedChange.id).where(
                DetectedChange.processed.is_(False), DetectedChange.is_baseline.is_(True)
            )
        )
    )
    if baseline_ids and not include_baseline:
        from sqlalchemy import update

        session.execute(
            update(DetectedChange)
            .where(DetectedChange.id.in_(baseline_ids))
            .values(processed=True)
        )
        session.flush()

    insights: list[Insight] = []
    for change in changes:
        try:
            insights.append(analyze_change(session, change))
        except Exception:
            log.exception("insight generation failed for change %s", change.id)
    log.info(
        "generated %d insights from %d changes (%d baseline changes suppressed)",
        len(insights),
        len(changes),
        len(baseline_ids),
    )
    return insights
