# Contract: Reportes del Libro Bancario HTTP/UI interface

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16

The module's only external interface is its server-rendered HTTP surface. All URL names are registered
without an `app_name` namespace (matching the existing `conciliacion/urls.py` convention so tests can
`reverse(...)` un-namespaced). All paths carry read-only `GET` semantics.

## URL map

| Name | Method | Path | Purpose |
|---|---|---|---|
| `reporte_libro` | GET | `/libro-bancario/reportes/` | On-screen printable HTML report (filters + table + totals) |
| `reporte_libro_csv` | GET | `/libro-bancario/reportes/csv/` | CSV download (`text/csv`) |
| `reporte_libro_excel` | GET | `/libro-bancario/reportes/excel/` | Excel `.xlsx` download |
| `reporte_libro_pdf` | GET | `/libro-bancario/reportes/pdf/` | PDF download |

## Common query parameters (all endpoints)

| Param | Type | Required | Meaning |
|---|---|---|---|
| `cuenta` | int | yes | `CuentaBancaria` primary key |
| `desde` | date (`YYYY-MM-DD`) | yes | inclusive range start |
| `hasta` | date (`YYYY-MM-DD`) | yes | inclusive range end |

`cuenta` is resolved with `get_object_or_404(CuentaBancaria, pk=cuenta)`. `desde` and `hasta` are
parsed with `django.forms.DateField` (or equivalent); invalid dates or `desde > hasta` produce a
validation failure surfaced as follows, and **no report is generated**.

## GET `reporte_libro` (HTML)

- Context contract passed to `conciliacion/reporte_libro.html`:
  - `form` — the filter form (bound when the request is invalid), Spanish labels.
  - `reporte` — a `ReporteLibro` (or `None` when no valid range was supplied).
  - Plus the account selector data so the operator can switch accounts.
- Status: 200 on render. Invalid range: 200 re-render with a Spanish inline error and no table,
  rather than a partial/empty report.

## Export endpoints (CSV / Excel / PDF)

- On success: `HttpResponse` with the correct MIME type, `Content-Disposition: attachment`, and a
  filename (`reporte_libro_<cuenta>_<desde>_<hasta>.<ext>`); status 200.
  - CSV: `text/csv; charset=utf-8` (UTF-8 BOM for Spanish Excel).
  - XLSX: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
  - PDF: `application/pdf`.
- Missing/invalid `cuenta`: 404 (`get_object_or_404`).
- Missing/invalid dates or `desde > hasta`: 400 with no body payload beyond an error indicator.
- Non-GET: 405 (consistent with the existing `emparejar_movimientos` / `libro_bancario_recalcular`
  patterns).

## Output fidelity (cross-format)

All four outputs MUST render the canonical report described in
[report-output.md](./report-output.md): identical rows, ordering, opening balance, totals, and closing
balance. The aggregation is computed by a single service function (`generar_reporte_libro`) shared by
every view, so this guarantee is structural rather than incidental.
