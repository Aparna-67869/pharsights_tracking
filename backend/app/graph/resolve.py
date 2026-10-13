"""Entity resolution: canonical Drugs, Sponsors and Patents across modules.

Every fact row that references a drug, sponsor or patent is linked to a
canonical entity. Canonicalisation uses normalized keys (salt-stripped drug
names, suffix-stripped company names, punctuation-free patent numbers) so the
same product mentioned in the FTF list, the Orange Book and the PDE list
resolves to one ``Drug`` row — which is what makes the 360-degree view and the
knowledge graph possible.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.text import (
    clean_text,
    normalize_company_name,
    normalize_drug_name,
    normalize_patent_number,
    title_case_drug,
)
from app.db.models import Drug, Patent, Sponsor

log = get_logger(__name__)


def infer_therapy_area(*names: str | None) -> str | None:
    """Always ``None`` — the platform does not guess therapy areas.

    The FDA/USPTO sources this platform ingests carry no therapy-area field, so
    there is no authoritative value to store. A drug's therapy area is left
    unset until a source that actually publishes one is wired in (e.g. a curated
    indication feed); it is never inferred from an ingredient's spelling, which
    produced wrong labels such as Abrocitinib (atopic dermatitis) → Oncology on
    the strength of the "nib" suffix.
    """
    return None


@dataclass
class ResolutionStats:
    drugs_created: int = 0
    drugs_matched: int = 0
    sponsors_created: int = 0
    sponsors_matched: int = 0
    patents_created: int = 0
    patents_matched: int = 0
    links: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "drugs_created": self.drugs_created,
            "drugs_matched": self.drugs_matched,
            "sponsors_created": self.sponsors_created,
            "sponsors_matched": self.sponsors_matched,
            "patents_created": self.patents_created,
            "patents_matched": self.patents_matched,
            "links": self.links,
        }


class EntityResolver:
    """Resolves and caches canonical entities for one session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.stats = ResolutionStats()
        self._drug_cache: dict[str, Drug] = {}
        self._sponsor_cache: dict[str, Sponsor] = {}
        self._patent_cache: dict[str, Patent] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        for drug in self.session.scalars(select(Drug)):
            self._drug_cache[drug.normalized_name] = drug
        for sponsor in self.session.scalars(select(Sponsor)):
            self._sponsor_cache[sponsor.normalized_name] = sponsor
        for patent in self.session.scalars(select(Patent)):
            self._patent_cache[patent.normalized_number] = patent

    # -- Drugs -------------------------------------------------------------

    def resolve_drug(
        self,
        name: str | None,
        *,
        ingredient: str | None = None,
        dosage_form: str | None = None,
        strength: str | None = None,
        route: str | None = None,
        rld_nda: str | None = None,
        sponsor_name: str | None = None,
        brand_name: str | None = None,
    ) -> Drug | None:
        display = clean_text(name) or clean_text(ingredient) or clean_text(brand_name)
        if not display:
            return None
        # Prefer the ingredient for identity; fall back to the display name.
        key_source = ingredient or display
        key = normalize_drug_name(key_source)
        if not key:
            key = normalize_drug_name(display)
        if not key:
            return None

        drug = self._drug_cache.get(key)
        if drug is None:
            drug = Drug(
                name=title_case_drug(display) or display,
                normalized_name=key,
                ingredient=clean_text(ingredient),
                dosage_form=clean_text(dosage_form),
                strength=clean_text(strength),
                route=clean_text(route),
                rld_nda=clean_text(rld_nda),
                therapy_area=infer_therapy_area(ingredient, display),
                brand_names=[clean_text(brand_name)] if brand_name else [],
                aliases=[],
            )
            self.session.add(drug)
            self.session.flush()
            self._drug_cache[key] = drug
            self.stats.drugs_created += 1
        else:
            self.stats.drugs_matched += 1
            changed = False
            for attribute, value in (
                ("ingredient", clean_text(ingredient)),
                ("dosage_form", clean_text(dosage_form)),
                ("strength", clean_text(strength)),
                ("route", clean_text(route)),
                ("rld_nda", clean_text(rld_nda)),
            ):
                if value and not getattr(drug, attribute):
                    setattr(drug, attribute, value)
                    changed = True
            if not drug.therapy_area:
                area = infer_therapy_area(ingredient, display)
                if area:
                    drug.therapy_area = area
                    changed = True
            brand = clean_text(brand_name)
            if brand:
                existing = list(drug.brand_names or [])
                if brand not in existing:
                    existing.append(brand)
                    drug.brand_names = existing
                    changed = True
            alias = clean_text(display)
            if alias and normalize_drug_name(alias) != key:
                aliases = list(drug.aliases or [])
                if alias not in aliases:
                    aliases.append(alias)
                    drug.aliases = aliases
                    changed = True
            if changed:
                self.session.flush()

        sponsor = self.resolve_sponsor(sponsor_name)
        if sponsor is not None and drug.sponsor_id is None:
            drug.sponsor_id = sponsor.id
            self.session.flush()
        return drug

    # -- Sponsors ----------------------------------------------------------

    def resolve_sponsor(self, name: str | None, *, sponsor_type: str | None = None) -> Sponsor | None:
        display = clean_text(name)
        if not display:
            return None
        key = normalize_company_name(display)
        if not key:
            return None
        sponsor = self._sponsor_cache.get(key)
        if sponsor is None:
            sponsor = Sponsor(
                name=display,
                normalized_name=key,
                sponsor_type=sponsor_type,
                aliases=[],
            )
            self.session.add(sponsor)
            self.session.flush()
            self._sponsor_cache[key] = sponsor
            self.stats.sponsors_created += 1
        else:
            self.stats.sponsors_matched += 1
            if display.casefold() != (sponsor.name or "").casefold():
                aliases = list(sponsor.aliases or [])
                if display not in aliases:
                    aliases.append(display)
                    sponsor.aliases = aliases
                    self.session.flush()
        return sponsor

    # -- Patents -----------------------------------------------------------

    def resolve_patent(
        self,
        patent_number: str | None,
        *,
        expiration_date=None,
        assignee: str | None = None,
        drug_substance_flag: bool | None = None,
        drug_product_flag: bool | None = None,
        patent_use_code: str | None = None,
        has_pte: bool | None = None,
        has_paragraph_iv: bool | None = None,
        pte_extension_days: int | None = None,
    ) -> Patent | None:
        number = normalize_patent_number(patent_number)
        if not number:
            return None
        patent = self._patent_cache.get(number)
        if patent is None:
            patent = Patent(
                patent_number=clean_text(patent_number) or number,
                normalized_number=number,
                patent_type="reissue" if number.startswith("RE") else "utility",
                assignee=clean_text(assignee),
                expiration_date=expiration_date,
                original_expiration_date=expiration_date,
                drug_substance_flag=drug_substance_flag,
                drug_product_flag=drug_product_flag,
                patent_use_code=clean_text(patent_use_code),
                has_pte=bool(has_pte),
                has_paragraph_iv=bool(has_paragraph_iv),
                pte_extension_days=pte_extension_days,
                family_members=[],
                litigation=[],
            )
            self.session.add(patent)
            self.session.flush()
            self._patent_cache[number] = patent
            self.stats.patents_created += 1
        else:
            self.stats.patents_matched += 1
            changed = False
            if expiration_date and (
                patent.expiration_date is None or expiration_date > patent.expiration_date
            ):
                patent.expiration_date = expiration_date
                changed = True
            if expiration_date and patent.original_expiration_date is None:
                patent.original_expiration_date = expiration_date
                changed = True
            if assignee and not patent.assignee:
                patent.assignee = clean_text(assignee)
                changed = True
            if drug_substance_flag is not None and patent.drug_substance_flag is None:
                patent.drug_substance_flag = drug_substance_flag
                changed = True
            if drug_product_flag is not None and patent.drug_product_flag is None:
                patent.drug_product_flag = drug_product_flag
                changed = True
            if patent_use_code and not patent.patent_use_code:
                patent.patent_use_code = clean_text(patent_use_code)
                changed = True
            if has_pte:
                patent.has_pte = True
                changed = True
            if has_paragraph_iv:
                patent.has_paragraph_iv = True
                changed = True
            if pte_extension_days and not patent.pte_extension_days:
                patent.pte_extension_days = pte_extension_days
                changed = True
            if changed:
                self.session.flush()
        return patent


def link_records(session: Session, *, batch_size: int = 2000) -> ResolutionStats:
    """Resolve canonical entities for every unlinked fact row.

    Idempotent: rows that already carry ``drug_id``/``patent_id``/``sponsor_id``
    are skipped, so this is safe to run on every pipeline execution.
    """
    from app.db.models import (
        ActiveMoiety,
        FtfRecord,
        OrangeBookPatent,
        OrangeBookProduct,
        PteApplication,
        PteCertificate,
    )

    resolver = EntityResolver(session)

    # --- FTF ---
    rows = list(
        session.scalars(
            select(FtfRecord).where(FtfRecord.is_active.is_(True), FtfRecord.drug_id.is_(None))
        )
    )
    for row in rows:
        drug = resolver.resolve_drug(
            row.drug_name,
            dosage_form=row.dosage_form,
            strength=row.strength,
            rld_nda=row.rld_nda,
            brand_name=row.rld_brand_name,
        )
        if drug is not None:
            row.drug_id = drug.id
            if row.sponsor_id is None:
                row.sponsor_id = drug.sponsor_id
        if row.patent_number:
            patent = resolver.resolve_patent(row.patent_number, has_paragraph_iv=True)
            if patent is not None:
                row.patent_id = patent.id
        resolver.stats.links += 1
    session.flush()

    # --- PTE applications ---
    rows = list(
        session.scalars(
            select(PteApplication).where(
                PteApplication.is_active.is_(True), PteApplication.drug_id.is_(None)
            )
        )
    )
    for row in rows:
        drug = resolver.resolve_drug(row.trade_name, ingredient=row.generic_name)
        if drug is not None:
            row.drug_id = drug.id
            if row.sponsor_id is None:
                row.sponsor_id = drug.sponsor_id
        patent = resolver.resolve_patent(row.patent_number, has_pte=True)
        if patent is not None:
            row.patent_id = patent.id
        resolver.stats.links += 1
    session.flush()

    # --- PTE certificates ---
    rows = list(
        session.scalars(
            select(PteCertificate).where(
                PteCertificate.is_active.is_(True), PteCertificate.drug_id.is_(None)
            )
        )
    )
    for row in rows:
        drug = resolver.resolve_drug(row.trade_name, ingredient=row.generic_name)
        if drug is not None:
            row.drug_id = drug.id
            if row.sponsor_id is None:
                row.sponsor_id = drug.sponsor_id
        patent = resolver.resolve_patent(
            row.patent_number,
            has_pte=True,
            pte_extension_days=row.extension_days,
            expiration_date=None,
        )
        if patent is not None:
            row.patent_id = patent.id
            if row.extended_expiration_date is None and patent.expiration_date:
                row.extended_expiration_date = patent.expiration_date
        resolver.stats.links += 1
    session.flush()

    # --- Active moieties ---
    rows = list(
        session.scalars(
            select(ActiveMoiety).where(
                ActiveMoiety.is_active.is_(True), ActiveMoiety.drug_id.is_(None)
            )
        )
    )
    for row in rows:
        sponsor = resolver.resolve_sponsor(row.sponsor_name)
        drug = resolver.resolve_drug(row.moiety_name, sponsor_name=row.sponsor_name)
        if drug is not None:
            row.drug_id = drug.id
        if sponsor is not None:
            row.sponsor_id = sponsor.id
        resolver.stats.links += 1
    session.flush()

    # --- Orange Book products ---
    rows = list(
        session.scalars(
            select(OrangeBookProduct).where(
                OrangeBookProduct.is_active.is_(True), OrangeBookProduct.drug_id.is_(None)
            )
        )
    )
    for row in rows:
        sponsor = resolver.resolve_sponsor(row.applicant_full_name or row.applicant)
        drug = resolver.resolve_drug(
            row.trade_name or row.ingredient,
            ingredient=row.ingredient,
            dosage_form=row.dosage_form_route,
            strength=row.strength,
            brand_name=row.trade_name,
            sponsor_name=row.applicant_full_name or row.applicant,
        )
        if drug is not None:
            row.drug_id = drug.id
        if sponsor is not None:
            row.sponsor_id = sponsor.id
        resolver.stats.links += 1
    session.flush()

    # --- Orange Book patents ---
    rows = list(
        session.scalars(
            select(OrangeBookPatent).where(
                OrangeBookPatent.is_active.is_(True), OrangeBookPatent.patent_id.is_(None)
            )
        )
    )
    for row in rows:
        patent = resolver.resolve_patent(
            row.patent_number,
            expiration_date=row.expiration_date,
            drug_substance_flag=row.drug_substance_flag,
            drug_product_flag=row.drug_product_flag,
            patent_use_code=row.patent_use_code,
        )
        if patent is not None:
            row.patent_id = patent.id
        resolver.stats.links += 1
    session.flush()

    log.info("entity resolution: %s", resolver.stats.to_dict())
    return resolver.stats
