# Feature Specification: Reportes del Libro Bancario (Bank Ledger Reports)

**Feature Branch**: `003-reportes-libro-bancario`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "New sub-module 'Reportes del Libro Bancario' for SENDA S.A. The mathematical engine and data entry are complete and validated; now we need to extract this data. Formats: PDF (printing) + Excel/CSV (accounting) + printable on-screen HTML view. Filters: date range + bank account. Layout/totals at the footer: opening balance + total Debe + total Haber + closing balance, with rows (fecha, tipo, detalle, debe, haber, saldo)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View a filtered ledger report on screen (Priority: P1)

A finance operator opens the "Reportes del Libro Bancario" module, selects a bank account and
a date range, and views that account's ledger movements for the range in a printable on-screen
(HTML) report. Each row shows `fecha`, `tipo_operacion`, `detalle`, `debe`, `haber` and `saldo`.
The footer shows the opening balance, total `debe`, total `haber` and closing balance.

**Why this priority**: The on-screen report is the base artifact; the Excel/CSV and PDF exports
are derived from the same filtered, ordered, totalled data and therefore depend on its correctness.

**Independent Test**: Can be fully tested by creating a `CuentaBancaria` with a known set of
`MovimientoLibro` records and rendering the report for a chosen range, verifying ordering, running
balance and footer totals — with no export or file download involved.

**Acceptance Scenarios**:

1. **Given** an account with movements across different dates, **When** the operator selects the
   account and a range `[desde, hasta]`, **Then** the report lists only the movements with
   `desde <= fecha <= hasta` (inclusive), ordered by `fecha` then `id`, each showing its stored `saldo`.
2. **Given** an account with movements dated before the range start, **When** the report is
   generated, **Then** the footer opening balance equals the running balance of the latest movement
   with `fecha < desde` (or the account's `saldo_inicial` when no such movement exists).
3. **Given** any range, **When** the report is generated, **Then** the footer shows the opening
   balance, total Debe (`Σ debe`), total Haber (`Σ haber`), and a closing balance equal to
   `opening + total Debe - total Haber` (equal to the last in-range movement's `saldo`, or equal to
   the opening balance when the range is empty).

---

### User Story 2 - Export the report to Excel/CSV (Priority: P2)

The operator exports the same filtered report to an Excel/CSV file for hand-off to accounting.

**Why this priority**: Excel/CSV is the recurring accounting delivery format and is the second
most frequent need after simply viewing the report.

**Independent Test**: Can be fully tested by generating a report for a known account + range and
verifying the exported file contains the identical rows, order, columns and footer totals as the
on-screen report.

**Acceptance Scenarios**:

1. **Given** an on-screen report for an account + range, **When** the operator triggers the
   Excel/CSV export, **Then** a downloadable file is produced with the same filtered rows in the
   same order and columns (`fecha`, `tipo_operacion`, `detalle`, `debe`, `haber`, `saldo`) and the
   same footer totals.
2. **Given** a range with no movements, **When** exporting to Excel/CSV, **Then** the file still
   contains the header row, the footer (opening balance, zeroed totals, closing balance) and no data rows.

---

### User Story 3 - Export the report to PDF (Priority: P3)

The operator exports the same filtered report to a PDF document for printing and archiving.

**Why this priority**: PDF is required for formal printing/archiving but is derived from the same
data as P1/P2; it is prioritized after the base data and spreadsheet export are correct.

**Independent Test**: Can be fully tested by generating a report for a known account + range and
verifying the PDF mirrors the on-screen report's rows, columns and footer totals in a print layout.

**Acceptance Scenarios**:

1. **Given** an on-screen report, **When** the operator triggers the PDF export, **Then** a
   printable PDF is produced that mirrors the on-screen report's rows, columns and footer totals.
2. **Given** a range with no movements, **When** exporting to PDF, **Then** the PDF renders the
   report header and footer (zeroed totals) with no data rows, without error.

---

### Edge Cases

- **Range with no matching movements**: ledger renders empty; the footer still shows the opening
  balance, `total debe = 0`, `total haber = 0` and `closing = opening`.
- **Range start before the account's first movement**: opening balance = `saldo_inicial`.
- **Movements on boundary dates**: rows where `fecha == desde` or `fecha == hasta` are included
  (inclusive range).
- **Invalid range** (`desde > hasta`): rejected with a clear Spanish validation message and no report produced.
- **Account with no movements at all**: report shows opening balance = `saldo_inicial`, no rows, zeroed totals.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow the operator to select exactly one `CuentaBancaria` and an
  inclusive date range (`fecha_desde`, `fecha_hasta`).
- **FR-002**: System MUST return only the `MovimientoLibro` rows whose `fecha` falls within the
  inclusive range, ordered by `fecha` then `id`.
- **FR-003**: System MUST render each row with the columns `fecha`, `tipo_operacion`, `detalle`,
  `debe`, `haber` and `saldo`.
- **FR-004**: System MUST compute the report opening balance as the running balance immediately
  before the range: the `saldo` of the latest movement with `fecha < fecha_desde`, or the account's
  `saldo_inicial` when no such movement exists.
- **FR-005**: System MUST compute the footer totals: opening balance, total Debe (`Σ debe`), total
  Haber (`Σ haber`), and closing balance = `opening + total Debe - total Haber`.
- **FR-006**: System MUST provide the report in three output formats: printable on-screen HTML,
  Excel/CSV, and PDF.
- **FR-007**: The Excel/CSV and PDF outputs MUST reproduce the same filtered rows, ordering,
  columns and footer totals as the on-screen report.
- **FR-008**: System MUST reject an invalid range (`fecha_desde > fecha_hasta`) with a user-facing
  validation message.
- **FR-009**: Reports MUST be strictly read-only; generating or exporting a report MUST NOT create,
  modify or delete any ledger or account data.
- **FR-010**: All monetary values (opening, totals, closing) MUST be computed with
  `decimal.Decimal` (never `float`) and displayed with the ledger's precision (2 decimal places).
- **FR-011**: All on-screen labels, column headers and messages of this module MUST be in Spanish;
  database identifiers remain Spanish; the specification and documentation remain English
  (project constitution).

### Key Entities *(include if feature involves data)*

- **MovimientoLibro** (read-only source): the ledger line providing `fecha`, `tipo_operacion`,
  `detalle`, `debe`, `haber` and the stored `saldo` for a `CuentaBancaria`.
- **CuentaBancaria** (read-only source): the selected account linking `Banco`, `TipoCuenta` and
  `Moneda`; provides `saldo_inicial` used for the opening balance when the range has no prior movements.
- No new persistent entities are introduced: the report is a derived, read-only projection of the
  existing data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can produce an on-screen report for any chosen account + date range in 3
  interactions or fewer.
- **SC-002**: 100% of generated reports order rows by `fecha`/`id` and render a closing balance
  equal to `opening + total Debe - total Haber`, exact to the cent with no floating-point drift.
- **SC-003**: Exported Excel/CSV and PDF files match the on-screen report row-for-row and
  total-for-total for the same inputs.
- **SC-004**: 0 ledger or account mutations result from report generation or export.

## Assumptions

- The report derives entirely from the existing, validated `MovimientoLibro` and `CuentaBancaria`
  models; no new database entities or migrations are introduced in v1.
- **"Saldo inicial"** in the footer means the *opening balance of the selected date range* (not the
  account's lifetime `saldo_inicial`), per FR-004. This is a documented default and should be
  confirmed by the Product Owner if a different convention is intended.
- The date range is inclusive on both boundaries.
- One account per report; multi-account consolidated reports are out of scope for v1, consistent
  with the chosen filter.
- Conciliation status (`conciliado`) is neither filtered nor displayed in v1 and is out of scope for
  this feature.
- Monetary precision is 2 decimal places, matching the `MovimientoLibro` `debe`/`haber`/`saldo`
  field precision.
- Output column headers and messages are in Spanish, matching the application's existing UI conventions.

