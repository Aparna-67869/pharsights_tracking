"""Shared export helpers (CSV / JSON download)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from fastapi.responses import StreamingResponse


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value)


def csv_response(
    rows: Iterable[Any],
    columns: list[str],
    *,
    filename: str,
    headers: list[str] | None = None,
) -> StreamingResponse:
    """Stream rows as a CSV download."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers or columns)
    for row in rows:
        writer.writerow([_cell(getattr(row, column, None)) for column in columns])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def xlsx_response(
    rows: Iterable[Any],
    columns: list[str],
    *,
    filename: str,
    headers: list[str] | None = None,
    sheet_name: str = "Export",
) -> StreamingResponse:
    """Stream rows as an .xlsx workbook."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name[:31]
    sheet.append(headers or columns)
    for row in rows:
        sheet.append([_cell(getattr(row, column, None)) for column in columns])

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
