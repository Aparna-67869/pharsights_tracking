"""Change-detection engine: the core SOP behaviour.

Covers the contract that the whole platform rests on:
  * first load of a source is a baseline and must not alert,
  * a revision produces exactly the added / updated / removed deltas present,
  * re-loading identical content is a no-op,
  * field-level diffs are recorded for updated rows.
"""

from __future__ import annotations

import datetime as dt

from app.db.models import DetectedChange, FtfRecord
from app.etl import load as loader

SOURCE = "fda_ftf_ppiv_excel"


def _ftf_record(**overrides) -> dict:
    # The parser hands validators real ``date`` objects (see app/parsers/ftf.py),
    # so fixtures must too — ``_date_sanity`` rejects strings.
    record = {
        "drug_name": "LIPITOR",
        "dosage_form": "Tablet",
        "strength": "20 mg",
        "rld_brand_name": "LIPITOR",
        "nda_number": "N021366",
        "date_of_submission": dt.date(2024, 1, 15),
        "number_of_andas": 3,
        "exclusivity_status": "Eligible",
        "decision_posting_date": dt.date(2024, 2, 1),
    }
    record.update(overrides)
    return record


def _load(session, records, *, is_baseline: bool):
    return loader.load_ftf(
        session, SOURCE, records, document=None, run_id=None, is_baseline=is_baseline
    )


def test_first_load_is_baseline_with_no_alerts(session):
    delta = _load(session, [_ftf_record()], is_baseline=True)

    assert delta.counts()["added"] == 1
    changes = session.query(DetectedChange).all()
    assert len(changes) == 1
    assert changes[0].change_type == "added"
    assert changes[0].is_baseline is True


def test_reload_of_identical_content_is_noop(session):
    _load(session, [_ftf_record()], is_baseline=True)
    session.flush()

    delta = _load(session, [_ftf_record()], is_baseline=False)

    assert delta.counts() == {"added": 0, "updated": 0, "removed": 0, "unchanged": 1, "total": 1}
    # Only the baseline change row exists.
    assert session.query(DetectedChange).count() == 1


def test_added_updated_removed_are_detected(session):
    _load(
        session,
        [
            _ftf_record(drug_name="DRUG A"),
            _ftf_record(drug_name="DRUG B"),
            _ftf_record(drug_name="DRUG C"),
        ],
        is_baseline=True,
    )
    session.flush()

    # DRUG A unchanged, DRUG B status changes, DRUG C drops out, DRUG D appears.
    delta = _load(
        session,
        [
            _ftf_record(drug_name="DRUG A"),
            _ftf_record(drug_name="DRUG B", exclusivity_status="Not Eligible"),
            _ftf_record(drug_name="DRUG D"),
        ],
        is_baseline=False,
    )

    counts = delta.counts()
    assert counts["added"] == 1
    assert counts["updated"] == 1
    assert counts["removed"] == 1
    assert counts["unchanged"] == 1

    by_type = {
        c.change_type: c
        for c in session.query(DetectedChange).filter(DetectedChange.is_baseline.is_(False))
    }
    assert set(by_type) == {"added", "updated", "removed"}

    updated = by_type["updated"]
    assert updated.field_changes == [
        {"field": "exclusivity_status", "before": "Eligible", "after": "Not Eligible"}
    ]
    assert updated.before["exclusivity_status"] == "Eligible"
    assert updated.after["exclusivity_status"] == "Not Eligible"


def test_removed_row_is_deactivated_not_deleted(session):
    _load(session, [_ftf_record(drug_name="DRUG C")], is_baseline=True)
    session.flush()

    _load(session, [], is_baseline=False)
    session.flush()

    rows = session.query(FtfRecord).all()
    assert len(rows) == 1
    # History is preserved for audit; the row is only flagged inactive.
    assert rows[0].is_active is False


def test_duplicate_rows_within_a_batch_are_collapsed(session):
    delta = _load(
        session,
        [_ftf_record(), _ftf_record()],
        is_baseline=True,
    )
    assert delta.counts()["added"] == 1
    assert delta.counts()["unchanged"] == 1
    # ``stored`` is the number of distinct keys persisted — the row count the
    # module serves, and what the provenance bar reports.
    assert delta.stored == 1


def test_invalid_rows_are_rejected_before_storage(session):
    delta = _load(
        session,
        [_ftf_record(), {"dosage_form": "Tablet"}],  # missing required drug_name
        is_baseline=True,
    )
    assert delta.counts()["added"] == 1
    assert session.query(FtfRecord).count() == 1
