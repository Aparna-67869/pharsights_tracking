"""Orange Book parsing correctness.

The tilde-delimited data files list one row per (application, product, patent,
use code) and per (application, product, exclusivity code, date). The natural
keys used to omit the use code and the exclusivity date, so
``sync_versioned_records`` silently merged distinct published rows — the patent
list collapsed 22,438 rows to 17,748 on a real load. These tests pin the keys
that keep every source row.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.parsers import orange_book as ob


def _patent_row(**overrides) -> dict:
    row = {
        "appl_type": "N",
        "appl_no": "021695",
        "product_no": "005",
        "patent_number": "9314447",
        "patent_use_code": "U-1447",
        "expiration_text": "May 31, 2033",
        "expiration_date": dt.date(2033, 5, 31),
    }
    row.update(overrides)
    return row


def test_patent_key_includes_use_code():
    """One patent can carry several use codes; each is a distinct source row."""
    assert ob.patent_source_key(_patent_row()) != ob.patent_source_key(
        _patent_row(patent_use_code="U-1448")
    )


def test_patent_key_is_stable_for_the_same_row():
    assert ob.patent_source_key(_patent_row()) == ob.patent_source_key(_patent_row())


def test_exclusivity_key_includes_date():
    """The same code can repeat for a product with different expiry dates."""
    base = {
        "appl_type": "N",
        "appl_no": "212273",
        "product_no": "002",
        "exclusivity_code": "ODE*",
    }
    assert ob.exclusivity_source_key(
        {**base, "exclusivity_date": dt.date(2027, 12, 21)}
    ) != ob.exclusivity_source_key({**base, "exclusivity_date": dt.date(2026, 10, 21)})


def test_product_key_is_unique_per_application_and_product():
    base = {"appl_type": "A", "appl_no": "078907", "product_no": "001"}
    assert ob.product_source_key(base) != ob.product_source_key(
        {**base, "product_no": "002"}
    )


def test_parse_patents_keeps_multi_use_code_rows():
    data = (
        b"Appl_Type~Appl_No~Product_No~Patent_No~Patent_Expire_Date_Text~"
        b"Drug_Substance_Flag~Drug_Product_Flag~Patent_Use_Code~Delist_Flag~Submission_Date\n"
        b"N~021695~005~9314447~May 31, 2033~~Y~U-1447~~2016-05-02\n"
        b"N~021695~005~9314447~May 31, 2033~~Y~U-1448~~2016-05-02\n"
    )
    records = ob.parse_patents(data)
    assert len(records) == 2
    assert len({ob.patent_source_key(r) for r in records}) == 2


def test_parse_exclusivity_keeps_same_code_different_dates():
    data = (
        b"Appl_Type~Appl_No~Product_No~Exclusivity_Code~Exclusivity_Date\n"
        b"N~212273~002~ODE*~Dec 21, 2027\n"
        b"N~212273~002~ODE*~Oct 21, 2026\n"
    )
    records = ob.parse_exclusivity(data)
    assert len(records) == 2
    assert len({ob.exclusivity_source_key(r) for r in records}) == 2


def test_run_pipeline_refuses_a_second_concurrent_run():
    """The scheduler, API and CLI share one single-flight slot.

    Without it a scheduled sweep and a manual trigger overlap, which on SQLite
    raises ``database is locked`` and leaves a run stuck in ``running``.
    """
    from app.core.errors import ConflictError
    from app.services import pipeline

    with pipeline._pipeline_lock:
        assert pipeline.pipeline_is_running() is True
        with pytest.raises(ConflictError):
            pipeline.run_pipeline(trigger="test")
    assert pipeline.pipeline_is_running() is False
