"""End-to-end change-detection demonstration against the live baseline.

Run with:  python -m scripts.demo_change

Proves the core SOP behaviour:
  1. The first load of a source is a baseline: no alerts.
  2. A subsequent document revision produces exactly the deltas present in the
     file — added, updated and removed rows — each with an AI impact analysis
     and a priority score.
  3. Only meaningful deltas reach the alert engine.
  4. Re-running against unchanged content is a no-op.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from app.alerts.engine import dispatch_alerts
from app.db.models import Alert, DetectedChange, FtfRecord, Insight
from app.db.session import session_scope
from app.etl import load as loader
from app.intelligence.engine import analyze_pending_changes
from app.parsers import ftf as ftf_parser
from app.services.pipeline import run_pipeline


def _row_to_record(row: FtfRecord) -> dict:
    return {
        "drug_name": row.drug_name,
        "dosage_form": row.dosage_form,
        "strength": row.strength,
        "rld_nda": row.rld_nda,
        "nda_number": row.nda_number,
        "rld_brand_name": row.rld_brand_name,
        "date_of_submission": row.date_of_submission,
        "number_of_andas": row.number_of_andas,
        "exclusivity_status": row.exclusivity_status,
        "decision_posting_date": row.decision_posting_date,
        "first_applicant_approval_date": row.first_applicant_approval_date,
        "first_commercial_marketing_date": row.first_commercial_marketing_date,
        "last_qualifying_patent_expiry": row.last_qualifying_patent_expiry,
        "certification_type": row.certification_type,
    }


def main() -> None:
    from app.db.session import create_all, drop_all

    drop_all()
    create_all()

    print("=" * 78)
    print("STEP 1 — initial load of every monitored source (baseline snapshot)")
    print("=" * 78)
    first = run_pipeline(trigger="demo-baseline")
    print(f"  changes recorded : {first.changes_detected}")
    print(f"  insights         : {first.insights_generated}")
    print(f"  alerts           : {first.alerts_created}   <- baseline never alerts")
    print()

    print("=" * 78)
    print("STEP 2 — re-run with unchanged sources (must be a no-op)")
    print("=" * 78)
    second = run_pipeline(trigger="demo-idempotency")
    print(f"  sources changed  : {second.sources_changed}")
    print(f"  changes recorded : {second.changes_detected}")
    print(f"  alerts           : {second.alerts_created}")
    print()

    print("=" * 78)
    print("STEP 3 — a new revision of the FTF list arrives")
    print("         (+1 new Paragraph IV filing, 1 status change, 1 removal)")
    print("=" * 78)
    with session_scope() as session:
        active = list(
            session.scalars(
                select(FtfRecord)
                .where(FtfRecord.is_active.is_(True), FtfRecord.source_code == "fda_ftf_ppiv_excel")
                .order_by(FtfRecord.drug_name)
            )
        )
        records = [_row_to_record(r) for r in active]

        # (a) A brand new Paragraph IV certification — blockbuster-class product.
        new_filing = dict(records[0])
        new_filing.update(
            {
                "drug_name": "Pembrolizumab",
                "rld_brand_name": "Keytruda",
                "nda_number": "125514",
                "rld_nda": "Keytruda 125514",
                "dosage_form": "Injection",
                "strength": "100 mg/4 mL",
                "date_of_submission": dt.date(2026, 10, 5),
                "number_of_andas": 14,
                "exclusivity_status": "Eligible",
                "last_qualifying_patent_expiry": dt.date(2028, 3, 15),
            }
        )

        # (b) An existing filing whose 180-day status changed.
        changed = dict(records[1])
        changed["exclusivity_status"] = "Extinguished"

        # (c) A filing withdrawn from the list.
        removed_key = ftf_parser.source_key(records[2])

        revised = [new_filing, changed] + records[3:]  # records[2] is dropped

        delta = loader.load_ftf(
            session,
            "fda_ftf_ppiv_excel",
            revised,
            document=None,
            run_id=None,
            is_baseline=False,
        )
        print(f"  delta: {delta.counts()}")

        insights = analyze_pending_changes(session)
        print(f"  insights generated: {len(insights)}")
        print()

        for insight in insights:
            print(f"  ┌─ [{insight.priority_label.upper()} {insight.priority_score}/100] {insight.title}")
            print(f"  │  What changed       : {insight.what_changed}")
            print(f"  │  Why it matters     : {insight.why_it_matters[:150]}")
            print(f"  │  Affected companies : {insight.affected_companies}")
            print(f"  │  Affected products  : {insight.affected_products}")
            print(f"  │  Generic opportunity: {insight.generic_opportunity}")
            print(f"  │  Exclusivity risk   : {insight.exclusivity_risk}")
            print(f"  │  Recommended action : {insight.recommended_action[:150]}")
            components = [
                f"{c['name']}={c['points']:.1f}" for c in insight.score_breakdown["components"]
            ]
            print(f"  └─ Score components  : {', '.join(components)}")
            print()

        alerts = dispatch_alerts(session, insights=insights)
        print(f"  alerts created and dispatched: {len(alerts)}")
        for alert in alerts:
            print(
                f"    • {alert.priority_label.upper():9s} {alert.priority_score:3d} | "
                f"{alert.event_type:12s} | channels={alert.channels_sent}"
            )

        total_changes = session.scalar(
            select(func.count()).select_from(DetectedChange)
        )
        total_insights = session.scalar(select(func.count()).select_from(Insight))
        total_alerts = session.scalar(select(func.count()).select_from(Alert))
        removed_detected = session.scalar(
            select(func.count())
            .select_from(DetectedChange)
            .where(DetectedChange.source_key == removed_key, DetectedChange.change_type == "removed")
        )
        print()
        print("=" * 78)
        print("TOTALS")
        print("=" * 78)
        print(f"  detected changes in audit log : {total_changes}")
        print(f"  insights generated            : {total_insights}")
        print(f"  alerts raised                 : {total_alerts}")
        print(f"  removal detected for {removed_key[:48]!r}: {removed_detected}")


if __name__ == "__main__":
    main()
