"""FTF parsing and reconciliation correctness.

The FDA Paragraph IV list has two quirks this module guards against:

* distinct filings share drug / dosage form / strength / NDA and differ only by
  the RLD/NDA brand (``Zepbound`` vs ``Zepbound (Autoinjector)``); and
* the Excel companion garbles in-cell line breaks as ``_x000D_`` and joins the
  ``DATE OF FIRST APPLICANT APPROVAL`` header into ``...APPLICANTAPPROVAL``.

Both previously caused real filings to be merged or blanked out.
"""

from __future__ import annotations

from app.core.text import clean_text
from app.parsers import ftf as ftf_parser
from app.parsers.excel import pick


def _excel(rows: list[dict]) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    headers = [
        "DRUG NAME",
        "DOSAGE FORM",
        "STRENGTH",
        "RLD/NDA",
        "DATE OF SUBMISSION",
        "NUMBER OF ANDAs SUBMITTED",
        "180-DAY STATUS",
        "180-DAY DECISION POSTING DATE",
        "DATE OF FIRST APPLICANTAPPROVAL",
        "DATE OF FIRST COMMERCIAL MARKETING BY FTF",
        "EXPIRATION DATE OF LAST QUALIFYING PATENT",
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Paragraph IV"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


ZEPBOUND_A = [
    "Tirzepatide", "Subcutaneous Solution", "2.5 mg/0.5 mL 5 mg/0.5 mL",
    "Zepbound (Autoinjector)\n217806", "5/13/2026", "12", None, None, None, None,
    "7/22/2039",
]
ZEPBOUND_B = [
    "Tirzepatide", "Subcutaneous Solution", "2.5 mg/0.5 mL 5 mg/0.5 mL",
    "Zepbound 217806", "5/13/2026", "3", None, None, None, None, "7/22/2039",
]
MULTIDOSE = [
    "Cisatracurium Besylate", "Injection", "2 mg/mL, 10 mL vial",
    "Nimbex 20551", "8/12/2009", "1", "Eligible", "2/11/2020", "8/18/2011",
    "8/19/2011", "5/14/2018",
]


def test_brand_differentiates_filings():
    """Two rows differing only by RLD brand must not collapse to one key."""
    records = ftf_parser.parse_ftf_excel(_excel([ZEPBOUND_A, ZEPBOUND_B]), filename="ppiv.xlsx")
    assert len(records) == 2
    keys = {ftf_parser.source_key(r) for r in records}
    assert len(keys) == 2
    brands = {r["rld_brand_name"] for r in records}
    assert brands == {"Zepbound", "Zepbound (Autoinjector)"}


def test_same_logical_filing_keeps_stable_key():
    """Re-publishing the same row must map onto the same natural key."""
    first = ftf_parser.parse_ftf_excel(_excel([ZEPBOUND_B]), filename="ppiv.xlsx")[0]
    second = ftf_parser.parse_ftf_excel(_excel([ZEPBOUND_B]), filename="ppiv.xlsx")[0]
    assert ftf_parser.source_key(first) == ftf_parser.source_key(second)


def test_excel_linebreak_artifacts_are_scrubbed():
    """``_x000D_`` markers and joined words must never reach the rendered fields."""
    row = ["Glyburide/\nMetformin Hydrochloride", "Tablets", "2.5 mg/500 mg",
           "Glucovance 21178", "Pre-MMA", None, None, None, None, None, None]
    record = ftf_parser.parse_ftf_excel(_excel([row]), filename="ppiv.xlsx")[0]
    blob = " ".join(str(v) for v in record["raw"].values())
    assert "_x000D_" not in blob
    assert "\n" not in (record["drug_name"] or "")
    assert record["drug_name"] == "Glyburide/ Metformin Hydrochloride"


def test_header_join_tolerance_matches_applicant_approval():
    """The Excel header omits the space before APPROVAL; the value must survive."""
    record = {
        "date of first applicantapproval": "2012-06-18 00:00:00",
        "date of first commercial marketing by ftf": "2012-06-19 00:00:00",
    }
    assert pick(record, "date of first applicant approval") == "2012-06-18 00:00:00"


def test_control_markers_removed_by_clean_text():
    assert clean_text("MetroGel-\nVaginal") == "MetroGel- Vaginal"
    assert clean_text("Excedrin _x000D_ (migraine)") == "Excedrin (migraine)"


def test_soft_hyphen_rejoined_without_touching_strengths():
    row = [MULTIDOSE[0], "Injection", "600 mg/50 mg/ 300 mg",
           "Nimbex 20551", "8/12/2009", "1", "Eligible", None, None, None, None]
    row[0] = "Cisatracurium Besylate (multi-\ndose)"
    record = ftf_parser.parse_ftf_excel(_excel([row]), filename="ppiv.xlsx")[0]
    assert record["drug_name"] == "Cisatracurium Besylate (multi-dose)"
    # multi-word strengths keep their internal spacing
    assert record["strength"] == "600 mg/50 mg/ 300 mg"
