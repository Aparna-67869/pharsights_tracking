"""PTE / PDE parsing correctness.

Both source workbooks contain rows that the natural keys used to merge, which
silently dropped real data: a single PTE application number is reused across
filing dates (``Grafapex`` 2021 and 2025), and a PDE moiety can be listed twice
for one sponsor with different issue dates (``Divalproex`` / ``Abbott``). The
USPTO certificate workbook also surfaces integer patent numbers as Excel floats
(``8088378.0``). These tests pin the corrected behaviour.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from app.core.text import canonical_identifier
from app.parsers import pde as pde_parser
from app.parsers import pte as pte_parser


def _xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---- identifier cleanup ----------------------------------------------------


def test_canonical_identifier_strips_excel_float():
    assert canonical_identifier("8088378.0") == "8088378"
    assert canonical_identifier("8088378.00") == "8088378"


def test_canonical_identifier_preserves_punctuated_and_alpha():
    assert canonical_identifier("RE27757") == "RE27757"
    assert canonical_identifier("7.420.051") == "7.420.051"
    assert canonical_identifier("11,411,158") == "11,411,158"
    assert canonical_identifier(None) is None


# ---- PTE applications ------------------------------------------------------


def _pte_app_workbook() -> bytes:
    return _xlsx(
        [
            "U.S. Application No.",
            "U.S. Patent No.",
            "Patent Center Link",
            "PTE Application Filing Date",
            "Trade Name Identified in PTE Application",
            "FDA/USDA Designated Number*",
        ],
        [
            ["10,129,352", "7199162", None, "09/23/2021", "Grafapex (glufosfamide)", None],
            ["10,129,352", "7199162", None, "02/28/2025", "Grafapex (glufosfamide)", "NDA-214759"],
            ["15,998,518", "11141158", None, "05/28/2024", "TriClip G4 System", "PMA-P230007"],
            ["15,998,518", "11141158", None, "02/25/2025", "TriClip G5 Delivery System", "PMA-P230007/S005"],
        ],
    )


def test_pte_application_number_reuse_is_preserved():
    records = pte_parser.parse_pte_applications(_pte_app_workbook(), filename="a.xlsx")
    keys = [pte_parser.source_key_application(record) for record in records]
    assert len(records) == 4
    assert len(set(keys)) == 4, "distinct applications must not collapse to one key"


def test_pte_application_ordinal_tracks_workbook_order():
    records = pte_parser.parse_pte_applications(_pte_app_workbook(), filename="a.xlsx")
    assert [record["source_ordinal"] for record in records] == [0, 1, 2, 3]


# ---- PTE certificates ------------------------------------------------------


def test_pte_certificate_patent_number_float_is_cleaned():
    data = _xlsx(
        ["Patent No", "Tradename of Product (generic name, if applicable)",
         "Original Expiration Date", "Period of Extension Granted"],
        [["8088378.0", "POLIVY (polatuzumab vedotin-piiq)", "08/05/2029", "1405 days"]],
    )
    records = pte_parser.parse_pte_certificates(data, filename="c.xlsx")
    assert records[0]["patent_number"] == "8088378"
    assert records[0]["patent_number_normalized"] == "8088378"
    assert records[0]["extension_days"] == 1405


# ---- PDE -------------------------------------------------------------------


def test_pde_same_moiety_sponsor_different_dates_are_preserved():
    data = _xlsx(
        ["Active Moiety", "Sponsor", "Date Issued"],
        [
            ["Divalproex", "Abbott Laboratories", "08/09/2002"],
            ["Divalproex", "Abbott Laboratories", "01/31/2006"],
        ],
    )
    records = pde_parser.parse_active_moieties(data, filename="p.xlsx")
    keys = [pde_parser.source_key(record) for record in records]
    assert len(records) == 2
    assert len(set(keys)) == 2
