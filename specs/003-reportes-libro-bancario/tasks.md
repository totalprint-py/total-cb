---
description: "Task list for Reportes del Libro Bancario (Bank Ledger Reports) — read-only report surface (HTML/CSV/XLSX/PDF) over the validated Libro Bancario engine"
---

# Tasks: Reportes del Libro Bancario (Bank Ledger Reports)

**Input**: Design documents from `/specs/003-reportes-libro-bancario/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/http-api.md, contracts/report-output.md, quickstart.md

**Tests**: REQUIRED — Constitution Principle 3 (Test-Driven Development, the Test-First imperative) mandates Red-Green-Refactor. Every aggregation function, view, exporter, and template writes a failing test before its implementation.

**Organization**: Phases follow the dependency order and TDD layering: setup → foundational aggregation (all stories share it) → US1 HTML (P1) → US2 Excel/CSV (P2) → US3 PDF (P3) → polish/verify. Each implementation task carries a `[US#]` label for traceability to the spec's user stories.

## Path Conventions

- **Project**: `totalcb/` (Django project) + `conciliacion/` (single app)
- **Tests**: `tests/unit/` at repo root (pytest + pytest-django, `conftest.py`)
- **Templates**: `conciliacion/templates/conciliacion/` (module templates) + `templates/base.html` (app shell)
- **Static**: `static/css/bootstrap.min.css`, `static/css/print.css` (reused, untouched)
- **New source files**: `conciliacion/reportes.py` (aggregation), `conciliacion/exportadores.py` (CSV/XLSX/PDF renderers)

> Note: plan.md sketched a single `tests/unit/test_reportes_libro.py`. This task list splits it into focused files (`..._agregacion.py`, `..._views.py`, `..._templates.py`, `..._exportadores.py`) mirroring feature 002's layering so each layer can be Red-Green'd and parallel-tested independently.

## Phase 1: Setup (verify reused infra + add deps)

**Purpose**: Confirm the reused engine/UI/test harness and add the two new pure-Python export dependencies.

- [ ] T001 [P] Confirm `totalcb/settings.py` already registers `conciliacion`, `LANGUAGE_CODE='es'`, `DECIMAL_SEPARATOR=','` / `THOUSAND_SEPARATOR='.'`, `FORMAT_MODULE_PATH=['totalcb.formats']`, `STATICFILES_DIRS=[BASE_DIR/'static']`, and SQLite `NAME=paths.database_path()` (absolute path — Principle 4). No change expected.
- [ ] T002 [P] Confirm `conciliacion/models.py` already defines `MovimientoLibro` (`save()` running-balance engine + `recalcular_saldos()`, `Meta.ordering=["fecha","id"]`) and `CuentaBancaria.saldo_inicial`; confirm `conciliacion/views.py` exposes the documented `get_object_or_404`/405 patterns. No change expected.
- [ ] T003 Add `fpdf` and `openpyxl` to `requirements.txt` and install with `venv\Scripts\pip install -r requirements.txt` (both pure Python, PyInstaller-safe — Principle 4).

**Checkpoint**: Engine, Spanish number formatting, and test harness verified; new dependencies available; nothing blocks the feature.

## Phase 2: Foundational — aggregation service (RED → GREEN)

**Purpose**: `conciliacion/reportes.py` is the single read-only aggregation consumed by all four outputs (FR-007/FR-009), so it must exist and be correct before any story.

- [ ] T004 Write failing `tests/unit/test_reportes_libro_agregacion.py`: `generar_reporte_libro()` filters rows by `cuenta` + `fecha__gte`/`fecha__lte` ordered `fecha`/`id` (FR-002); opening balance = latest prior `saldo` with `fecha < desde`, else `saldo_inicial` (FR-004); `total_debe`/`total_haber`/`saldo_final = saldo_inicial_periodo + total_debe - total_haber` (FR-005); empty range yields `Decimal("0.00")` totals and `saldo_final == saldo_inicial_periodo`; `fecha_desde > fecha_hasta` raises `RangoFechasInvalidoError` (FR-008); all math via `decimal.Decimal`, never `float` (FR-010); call makes no writes (FR-009).
- [ ] T005 Implement `conciliacion/reportes.py`: `RangoFechasInvalidoError`, frozen `ReporteLibro` result type (`cuenta`, `fecha_desde`, `fecha_hasta`, `movimientos`, `saldo_inicial_periodo`, `total_debe`, `total_haber`, `saldo_final`), and `generar_reporte_libro(*, cuenta, fecha_desde, fecha_hasta)` per data-model.md derivation rules.

**Checkpoint**: `pytest tests/unit/test_reportes_libro_agregacion.py` passes (Green); the canonical result is available to every story.

## Phase 3: User Story 1 — View a filtered ledger report on screen (Priority: P1) 🎯 MVP

**Goal**: Operator selects an account + inclusive date range and sees the printable HTML report (rows `fecha/tipo/detalle/debe/haber/saldo` + `Saldo inicial`/`Total Debe`/`Total Haber`/`Saldo final` footer).

**Independent Test**: Create a `CuentaBancaria` + known `MovimientoLibro` rows and render `reporte_libro` for a range, verifying filter/order, running balance, and footer totals — no export involved.

### Tests for User Story 1 (write first, ensure they FAIL) ⚠️

- [ ] T006 [P] [US1] Write failing `tests/unit/test_reporte_libro_views.py` (US1 portion): GET `reporte_libro` returns 200 with context `form`, `reporte`, account selector; valid range filters/orders; missing/invalid `cuenta` → 404 (`get_object_or_404`); invalid `desde`/`hasta` or `desde > hasta` re-renders with the bound form + Spanish inline error and no table; non-GET → 405.
- [ ] T007 [P] [US1] Write failing `tests/unit/test_reporte_libro_templates.py`: render `conciliacion/reporte_libro.html`; assert Spanish columns `Fecha`/`Tipo`/`Detalle`/`Debe`/`Haber`/`Saldo` and footer labels `Saldo inicial`/`Total Debe`/`Total Haber`/`Saldo final`; `saldo` column not editable; filter bar carries `no-print`; an empty-range `Sin movimientos en el rango seleccionado.` row; a `window.print()` action (FR-001/003/011).

### Implementation for User Story 1

- [ ] T008 [P] [US1] Add `ReporteLibroForm` to `conciliacion/forms.py`: fields `cuenta` (ModelChoiceField), `desde` + `hasta` (`DateField`, `widget=DateInput(attrs={"type": "date"})`), Spanish labels and `form-control`/`form-select` classes consistent with existing forms (FR-001).
- [ ] T009 [US1] Implement the `reporte_libro` view in `conciliacion/views.py`: `get_object_or_404(CuentaBancaria, pk=cuenta)`, parse `desde`/`hasta`, call `generar_reporte_libro`, catch `RangoFechasInvalidoError` → re-render with bound `ReporteLibroForm` + Spanish message and `reporte=None`; non-GET → 405 (contracts/http-api.md).
- [ ] T010 [P] [US1] Create `conciliacion/templates/conciliacion/reporte_libro.html`: `no-print` filter bar + high-contrast print-friendly table (columns `fecha`, `tipo_operacion`, `detalle`, `debe`, `haber`, `saldo`) + totals footer (`Saldo inicial`, `Total Debe`, `Total Haber`, `Saldo final`) + empty-state row, reusing `print.css` (FR-003/005).
- [ ] T011 [US1] Register `path("libro-bancario/reportes/", views.reporte_libro, name="reporte_libro")` in `conciliacion/urls.py`, un-namespaced like the existing routes.
- [ ] T012 [P] [US1] Add the "Reportes Bancarios" entry to `templates/base.html` sidebar navigation (Spanish label, consistent with existing entries).

**Checkpoint**: `pytest tests/unit/test_reporte_libro_views.py tests/unit/test_reporte_libro_templates.py` passes (Green); the on-screen MVP renders end-to-end. T008/T009 share `conciliacion/forms.py`+`views.py` (sequential); T010/T012 are parallel.

## Phase 4: User Story 2 — Export the report to Excel/CSV (Priority: P2)

**Goal**: Operator downloads the same filtered report as Excel (`.xlsx`) or CSV for hand-off to accounting.

**Independent Test**: Generate a report for a known account + range and verify the exported file contains identical rows, order, columns, and footer totals as the on-screen report (FR-007).

### Tests for User Story 2 (write first, ensure they FAIL) ⚠️

- [ ] T013 [P] [US2] Write failing `tests/unit/test_exportadores_libro.py` (CSV/XLSX portion): CSV is UTF-8 with BOM, semicolon-delimited, decimal-comma, header + footer rows, and preserves the empty-range footer; XLSX has native numeric cells (summable, 2-dp display) with header + footer rows and the empty-range footer; both mirror the aggregation's rows/order/totals (FR-007, contracts/report-output.md).
- [ ] T014 [P] [US2] Write failing `tests/unit/test_reporte_libro_views.py` (US2 portion): GET `reporte_libro_csv` → 200 with `text/csv; charset=utf-8` + `Content-Disposition: attachment`; GET `reporte_libro_excel` → 200 with XLSX MIME + attachment; missing/invalid `cuenta` → 404; invalid dates or `desde > hasta` → 400; non-GET → 405.

### Implementation for User Story 2

- [ ] T015 [US2] Implement `exportar_csv(reporte)` and `exportar_xlsx(reporte)` in `conciliacion/exportadores.py`: both consume a `ReporteLibro`, render identical rows/columns/footer, and return the encoded bytes/string (CSV via stdlib `csv` + UTF-8 BOM + semicolon/decimal-comma; XLSX via `openpyxl` with numeric 2-dp cells) — contracts/report-output.md.
- [ ] T016 [US2] Implement the `reporte_libro_csv` and `reporte_libro_excel` views in `conciliacion/views.py`: resolve `cuenta`, parse `desde`/`hasta`, call `generar_reporte_libro`, stream `HttpResponse` with the correct MIME + `Content-Disposition: attachment` + filename `reporte_libro_<cuenta>_<desde>_<hasta>.<ext>`; `RangoFechasInvalidoError` → 400; non-GET → 405.
- [ ] T017 [US2] Register `path("libro-bancario/reportes/csv/", views.reporte_libro_csv, name="reporte_libro_csv")` and `path("libro-bancario/reportes/excel/", views.reporte_libro_excel, name="reporte_libro_excel")` in `conciliacion/urls.py`.

**Checkpoint**: `pytest tests/unit/test_exportadores_libro.py tests/unit/test_reporte_libro_views.py` passes (Green). T015/T016 share `conciliacion/exportadores.py`+`views.py` (sequential); T017 depends on T016.

## Phase 5: User Story 3 — Export the report to PDF (Priority: P3)

**Goal**: Operator downloads the same report as a printable/archivable PDF via `fpdf2`.

**Independent Test**: Generate a report for a known account + range and verify the PDF mirrors the on-screen report's rows, columns, and footer totals, including the empty-range case.

### Tests for User Story 3 (write first, ensure they FAIL) ⚠️

- [ ] T018 [P] [US3] Write failing `tests/unit/test_exportadores_libro.py` (PDF portion): `exportar_pdf(reporte)` returns valid PDF bytes (`%PDF` magic) rendering the report header, rows, and `Saldo inicial`/`Total Debe`/`Total Haber`/`Saldo final` footer with locale strings; empty range renders header + zeroed footer without error (FR-006/007, report-output.md).
- [ ] T019 [P] [US3] Write failing `tests/unit/test_reporte_libro_views.py` (US3 portion): GET `reporte_libro_pdf` → 200 with `application/pdf` + `Content-Disposition: attachment`; missing/invalid `cuenta` → 404; invalid dates or `desde > hasta` → 400; non-GET → 405.

### Implementation for User Story 3

- [ ] T020 [US3] Implement `exportar_pdf(reporte)` in `conciliacion/exportadores.py` using `fpdf2`: landscape/portrait table with header, the six report columns, and the totals footer rendered with the same Spanish-locale strings as HTML (contracts/report-output.md).
- [ ] T021 [US3] Implement the `reporte_libro_pdf` view in `conciliacion/views.py`: share `generar_reporte_libro`, stream `HttpResponse(content_type="application/pdf")` with attachment `Content-Disposition` + filename `reporte_libro_<cuenta>_<desde>_<hasta>.pdf`; `RangoFechasInvalidoError` → 400; non-GET → 405.
- [ ] T022 [US3] Register `path("libro-bancario/reportes/pdf/", views.reporte_libro_pdf, name="reporte_libro_pdf")` in `conciliacion/urls.py`.

**Checkpoint**: `pytest tests/unit/test_exportadores_libro.py tests/unit/test_reporte_libro_views.py` passes (Green); all three formats consumed the single canonical aggregation.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Full-suite verification, manual validation, and desktop-readiness checks.

- [ ] T023 Run the full suite `python -m pytest -q` (all green; no regressions in the existing `test_movimiento_libro.py`, `test_libro_bancario_*.py`, engine, and view suites).
- [ ] T024 [P] Execute `quickstart.md` manual scenarios 1–6 (HTML view + footer totals, `window.print()`, CSV/XLSX/PDF downloads, `desde > hasta` Spanish error, empty range, boundary dates, first-range `saldo_inicial`).
- [ ] T025 [P] Run `python manage.py makemigrations --check` (confirm **no new migrations** — read-only projection) and `python manage.py collectstatic --noinput` (desktop readiness, Principle 4).

**Checkpoint**: Feature complete; SC-001…SC-004 verifiable.

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies — can start immediately.
- **Phase 2 (Foundational)**: depends on Phase 1; BLOCKS all user stories.
- **Phase 3 (US1)**, **Phase 4 (US2)**, **Phase 5 (US3)**: all depend on Phase 2's `reportes.py`; each is an independent increment and may proceed sequentially in priority order (P1 → P2 → P3).
- **Phase 6 (Polish)**: depends on all desired stories.

### User Story Dependencies

- **US1 (P1)**: after Phase 2; no dependency on US2/US3 — MVP.
- **US2 (P2)**: after Phase 2; independently testable via the exports.
- **US3 (P3)**: after Phase 2; independent of US1/US2 except that all read the same `generar_reporte_libro`.

### Within Each User Story

- Tests MUST be written and confirmed FAILING before implementation (Principle 3 Red-Green-Refactor).
- Aggregation (`reportes.py`) before views/exporters; exporters before export views.
- Same-file tasks are sequential (not `[P]`): `conciliacion/views.py` (T009 → T016 → T021), `conciliacion/exportadores.py` (T015 → T020), `conciliacion/urls.py` (T011 → T017 → T022), `tests/unit/test_reporte_libro_views.py` (T006 → T014 → T019), `tests/unit/test_exportadores_libro.py` (T013 → T018).

### Parallel Opportunities

- Within US1: T006/T007 (different test files) in parallel; then T008 (forms.py), T010 (template), T012 (base.html) are all `[P]`.
- Within US2/US3: `test_exportadores_libro.py` vs `test_reporte_libro_views.py` are `[P]` with each other.
- Once Phase 2 completes, US1/US2/US3 implementation files (`forms.py`, `exportadores.py`, `templates/`, `base.html`) can be worked by different team members — respecting the same-file sequences above.

## Story → Task Traceability

| Story | Tasks |
|---|---|
| US1 (on-screen HTML report) | T004, T005, T006, T007, T008, T009, T010, T011, T012 |
| US2 (Excel/CSV export) | T004, T005, T013, T014, T015, T016, T017 |
| US3 (PDF export) | T004, T005, T018, T019, T020, T021, T022 |

## Notes

- Money is `decimal.Decimal` (2 dp); `float` is forbidden (FR-010, Principle 5). The report never re-derives balances from scratch — each row's stored `saldo` is authoritative, and the footer follows the implemented engine convention `saldo_final = saldo_inicial_periodo + total_debe - total_haber` (R4).
- The report is strictly read-only (FR-009): no `create`/`update`/`delete`, and `makemigrations --check` must stay clean.
- `desde`/`hasta` are inclusive on both boundaries (spec Assumptions); invalid order is the only new validation and surfaces as `RangoFechasInvalidoError` (HTML: Spanish inline error; exports: 400).
- CSV uses stdlib `csv` with UTF-8 BOM, semicolon delimiter, decimal comma; XLSX uses `openpyxl` numeric cells; PDF uses `fpdf2` — all PyInstaller-safe and streamed, never written to disk (Principle 4).
- Spanish identifiers/UI strings only (`ReporteLibro`, `generar_reporte_libro`, `exportar_csv`, "Saldo inicial", …); docs remain English (Principle 0).
- **Open question (non-blocking)**: the "Saldo inicial" footer convention = opening balance of the selected range (not the account lifetime `saldo_inicial`), per FR-004 and spec Assumptions; confirm with the Product Owner via `/speckit-clarify` if desired.



