# Implementation Plan: Reportes del Libro Bancario (Bank Ledger Reports)

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-reportes-libro-bancario/spec.md`

## Summary

Add a read-only reporting surface over the already-validated **Libro Bancario** engine. The operator
selects a `CuentaBancaria` and an inclusive date range and obtains the account's `MovimientoLibro` rows
ordered by `fecha`/`id`, with a footer of `saldo inicial` (opening balance) + total `debe` + total
`haber` + `saldo final`. The **same** aggregated result is rendered in four outputs: printable
on-screen HTML, CSV, Excel (`.xlsx`), and PDF. Aggregation lives in a new read-only service, thin views
adapt HTTP, two pure-Python dependencies (`fpdf`, `openpyxl`) are added and CSV uses the standard
library. **No database schema changes** — the report is a derived, in-memory projection.

## Technical Context

**Language/Version**: Python 3.14 (Django 6.0.7; `requirements.txt` pins `Django>=5.1,<7.0`)

**Primary Dependencies**: Django, offline Bootstrap 5, Alpine.js v3, PyInstaller; **new** `fpdf` (PDF)
and `openpyxl` (XLSX); standard library `csv`

**Storage**: SQLite (single `.db`, absolute path via `totalcb/paths.py`)

**Testing**: pytest + pytest-django (TDD Red-Green-Refactor)

**Target Platform**: Windows 10/11 (compiled single `.exe`)

**Project Type**: Desktop web application (local Django app, frozen with PyInstaller)

**Performance Goals**: Correctness over speed (single internal user); sub-second render/export for
thousands of ledger rows

**Constraints**: Offline; no client-side build step; `decimal.Decimal` arithmetic (2 dp); Spanish locale
numbers (comma decimal, dot thousands); strictly read-only; PyInstaller-safe (pure-Python) dependencies

**Scale/Scope**: 1 report page + 3 download endpoints + 1 aggregation service + 1 export module; no new
models or migrations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle 0 — Language Strictness (CRITICAL)**: PASS — docs/plan in English; identifiers and UI
  strings in Spanish (`ReporteLibro`, `saldo_inicial`, "Reportes del Libro Bancario").
- **Principle 1 — Database Integrity**: PASS — no new DB schema; the only new validation (date-range
  order, FR-008) is request scoping, enforced at the service layer (not a stored invariant). Existing
  tables already use `CheckConstraint(condition=Q(...))`.
- **Principle 2 — Integrated Frontend**: PASS — offline Bootstrap 5 + Alpine.js, no build step
  (constitution v2.0.0 now mandates Bootstrap 5).
- **Principle 3 — TDD**: PASS — failing tests first for aggregation, endpoints, and exporters.
- **Principle 4 — Desktop Readiness**: PASS — `fpdf` and `openpyxl` are pure Python (no native wheels)
  and bundle cleanly under PyInstaller; assets via `{% static %}`; exports stream bytes and write no
  files to disk.
- **Principle 5 — Financial Precision & Zero-Sum**: PASS — all report math uses `decimal.Decimal`
  (2 dp); `saldo_final = saldo_inicial_periodo + total_debe - total_haber`.

*Post-design re-check*: PASS; no violations.

## Architectural Components

### 1. Aggregation service (new, read-only) — `conciliacion/reportes.py`

Pure domain logic with no HTTP or ORM write concerns:

- `RangoFechasInvalidoError` — domain error raised when `fecha_desde > fecha_hasta`.
- `ReporteLibro` — a frozen result type holding `cuenta`, `fecha_desde`, `fecha_hasta`,
  `movimientos`, `saldo_inicial_periodo`, `total_debe`, `total_haber`, and the computed `saldo_final`.
- `generar_reporte_libro(*, cuenta, fecha_desde, fecha_hasta) -> ReporteLibro` — runs the filter,
  computes the opening balance (latest `saldo` with `fecha < desde`, else `saldo_inicial`), and the
  totals. Reuses `decimal.Decimal` and rejects any `float`.

### 2. File renderers (new) — `conciliacion/exportadores.py`

Pure functions that take a `ReporteLibro` and return bytes (or CSV text):

- `a_csv(reporte) -> str` — semicolon-delimited, decimal-comma, UTF-8 BOM.
- `a_xlsx(reporte) -> bytes` — openpyxl workbook, numeric cells, 2-decimal format, header + footer.
- `a_pdf(reporte) -> bytes` — fpdf2 table with header and the totals footer.

### 3. Thin views (new) — `conciliacion/views.py` additions

HTTP adapters that resolve inputs (query params), delegate to the service, and delegate rendering:

- `reporte_libro` (GET): render the on-screen printable HTML report for `cuenta` + `desde` + `hasta`.
- `reporte_libro_csv` (GET): stream a `text/csv` attachment.
- `reporte_libro_excel` (GET): stream an `.xlsx` attachment.
- `reporte_libro_pdf` (GET): stream a `application/pdf` attachment.

Invalid/missing params and invalid ranges surface as a validated error (the HTML view re-renders a
Spanish message; the export views return 400) — no partial report is ever produced.

### 4. Report filters form + templates (new)

- `ReporteLibroForm` (or inline filter fields, per spec FR-001/FR-002): `cuenta`, `desde`, `hasta`.
- `conciliacion/templates/conciliacion/reporte_libro.html`: filter bar (no-print), report table with
  columns `fecha`, `tipo`, `detalle`, `debe`, `haber`, `saldo`, and the footer row (`Saldo inicial`,
  `Total Debe`, `Total Haber`, `Saldo final`). Reuses the existing `print.css` (`no-print`) and a table
  layout consistent with `reporte_manual.html` for high-contrast printing.

### 5. Sidebar integration

Add a "Reportes Bancarios" entry to `templates/base.html`, consistent with existing nav entries.

### 6. Requirements + tests

- Add `fpdf` and `openpyxl` to `requirements.txt`.
- `tests/unit/test_reportes_libro.py`: aggregation (filtering, opening balance, totals, empty range,
  invalid range), CSV/XLSX/PDF exporters, and the four views' status/content-disposition guarantees.

## Project Structure

### Documentation (this feature)

```text
specs/003-reportes-libro-bancario/
├── plan.md              # this file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── http-api.md      # Phase 1 output (endpoints/params)
│   └── report-output.md # Phase 1 output (shared report contract)
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
totalcb/                 # Django project
├── settings.py          # Spanish number formatting (comma/dot) already configured
├── paths.py             # absolute SQLite/static path helper
└── urls.py

conciliacion/            # Django app
├── models.py            # MovimientoLibro (engine) + CuentaBancaria (existing, unchanged)
├── forms.py             # + ReporteLibroForm (filter fields, Spanish labels)
├── reportes.py          # NEW: aggregation service + ReporteLibro + domain error
├── exportadores.py      # NEW: a_csv / a_xlsx / a_pdf byte renderers
├── views.py             # + reporte_libro (HTML) and 3 download views
├── urls.py              # + reporte_libro_* URL patterns
├── templates/conciliacion/
│   └── reporte_libro.html     # NEW: filters (no-print) + report table + footer totals
└── static/ (bundled at root; reuses bootstrap.min.css + print.css)

templates/
└── base.html            # + "Reportes Bancarios" sidebar entry

static/
├── css/bootstrap.min.css
├── css/print.css
└── js/alpine.min.js

tests/
└── unit/test_reportes_libro.py   # NEW: aggregation + exporters + views (TDD)
```

**Structure Decision**: Single Django project + single `conciliacion` app (single-enterprise desktop
scope). The report is a **read-only projection**, so business logic lives in a dedicated aggregation
module (`reportes.py`) — mirroring the 001 `services.py` rule that arithmetic stays out of views and
models — and the three file renderers stay in `exportadores.py` so every format consumes one canonical
result.

