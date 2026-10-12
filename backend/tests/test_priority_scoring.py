"""Priority scoring — the rule that decides which changes are worth alerting on.

The score is a pure weighted sum, so these are exact-value assertions rather
than ranges. They encode the product decision that "only meaningful alerts reach
users": a blockbuster exclusivity event must outrank an obscure one, and the
band boundaries must not drift.
"""

from __future__ import annotations

import datetime as dt

from app.intelligence.priority import WEIGHTS, compute_priority, label_for

TODAY = dt.date.today()


def test_label_bands_match_the_spec():
    assert label_for(100) == "critical"
    assert label_for(90) == "critical"
    assert label_for(89) == "high"
    assert label_for(70) == "high"
    assert label_for(69) == "medium"
    assert label_for(40) == "medium"
    assert label_for(39) == "low"
    assert label_for(0) == "low"


def test_weights_sum_to_one_hundred():
    # The bands above only make sense if the weighted sum can reach 100.
    assert sum(WEIGHTS.values()) == 100


def test_high_signal_event_scores_above_low_signal_event():
    high = compute_priority(
        patent={"drug_substance_flag": True, "patent_use_code": "U-1234", "has_pte": True},
        sponsor_name="Pfizer",
        drug_name="Keytruda",
        therapy_area="oncology",
        challenger_count=12,
        expiry=TODAY + dt.timedelta(days=120),
        exclusivity_status="Eligible",
        has_pte=True,
        occurred_at=TODAY,
    )
    low = compute_priority(
        sponsor_name="Tiny Pharma LLC",
        drug_name="obscure molecule",
        occurred_at=TODAY - dt.timedelta(days=400),
    )

    assert high.total > low.total
    assert high.total >= 70, high.to_dict()
    assert low.total < 70, low.to_dict()


def test_score_is_clamped_and_bounded():
    score = compute_priority(
        patent={"drug_substance_flag": True, "drug_product_flag": True,
                "patent_use_code": "U-1", "has_pte": True},
        sponsor_name="Merck",
        drug_name="Keytruda",
        therapy_area="oncology",
        challenger_count=50,
        expiry=TODAY,
        exclusivity_status="Eligible",
        has_pte=True,
        occurred_at=TODAY,
    )
    assert 0 <= score.total <= 100
    assert score.label == label_for(score.total)


def test_every_component_carries_a_reason_for_the_explanation():
    score = compute_priority(drug_name="Humira", sponsor_name="AbbVie", occurred_at=TODAY)
    names = {c.name for c in score.components}
    assert names == set(WEIGHTS)
    for component in score.components:
        assert component.reason, f"{component.name} has no reason"
        assert 0.0 <= component.raw <= 1.0
    # The AI impact narrative is built from these reasons, so serialisation must
    # round-trip.
    payload = score.to_dict()
    assert payload["total"] == score.total
    assert len(payload["components"]) == len(WEIGHTS)
