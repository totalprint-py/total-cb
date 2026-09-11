# Feature Specification: Phase 1 - Core Reconciliation Engine

**Feature Branch**: `001-core-reconciliation-engine`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Phase 1 - Core Reconciliation Engine"

## Clarifications

### Session 2026-09-04

- Q: How should bank deposits that are waiting on sales-department receipts be handled without
  dropping them from the pending list? → A: Admins may flag a `MovimientoBancario` as "En
  Consulta" (under investigation) to visually isolate it while it remains in the pending list.
- Q: Do users need a lightweight way to annotate individual movements? → A: Add a simple
  free-text field `notas` (notes) to both `MovimientoBancario` and `MovimientoInterno` as
  digital "post-its".
- Q: How strict must amount matching be relative to date matching? → A: Amounts are matched
  exactly to the cent (ruthless), while dates are completely permissive — records spanning
  weeks apart may be matched; the UI may warn but MUST never block the action.
- Q: Which UX surfaces must the reconciliation feature provide? → A: A split-screen digital
  matching interface AND a printer-friendly "Manual Checking Report" view that uses CSS print
  media queries to hide sidebars and backgrounds.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a bank reconciliation (Priority: P1)

The finance operator imports bank movements (`MovimientoBancario`) and internal movements
(`MovimientoInterno`) for a given account and period, then runs the reconciliation. The
system matches the two sides, produces a `Conciliacion` header with the corresponding
`DetalleConciliacionBancaria` and `DetalleConciliacionInterna` lines, and enforces the
Zero-Sum equation. If the equation does not hold exactly, the entire operation is rolled
back and nothing is persisted.

**Why this priority**: This is the core value of the product. Without a correct,
transactional reconciliation engine nothing else matters.

**Independent Test**: Can be fully tested by loading a controlled set of bank and internal
movements and running reconciliation, verifying the resulting `Conciliacion` and its details
without any catalog or UI features.

**Acceptance Scenarios**:

1. **Given** imported bank and internal movements for the same account and period, **When**
   the operator runs reconciliation, **Then** the system creates a `Conciliacion` with
   matched `DetalleConciliacionBancaria`/`DetalleConciliacionInterna` pairs and reports any
   unmatched items, and the Zero-Sum equation `Sum(Bancario) - Sum(Interno) + Sum(Ajustes)
   == 0` holds.
2. **Given** totals that do not satisfy the Zero-Sum equation, **When** the reconciliation
   attempts to commit, **Then** the entire transaction is rolled back, no `Conciliacion` or
   detail is persisted, and the operator sees a clear error.

---

### User Story 2 - Maintain master catalogs (Priority: P2)

The administrator maintains the reference catalogs `Banco`, `TipoCuenta`, `Moneda`,
`TipoOperacion`, and `ConceptoAjuste`. Each catalog enforces stable unique codes,
descriptive labels, and data-integrity rules (notably the decimal precision of each
currency).

**Why this priority**: Reference data is the foundation every financial record and the
reconciliation engine depends on; incorrect catalogs corrupt the entire ledger.

**Independent Test**: Can be fully tested by creating, editing, and attempting invalid
catalog entries and confirming integrity rules hold, without importing any movement.

**Acceptance Scenarios**:

1. **Given** an administrator, **When** creating or editing a `Moneda`, **Then** the field
   `cantidad_decimales` is required and validated (e.g., a non-negative integer) so that all
   amounts in that currency use that precision.
2. **Given** an administrator, **When** a catalog code is duplicated or invalid, **Then**
   the system rejects the entry with a validation error.

---

### User Story 3 - Record reconciliation adjustments (Priority: P3)

To close residual differences, the operator records `AjusteConciliacion` entries classified
by a `ConceptoAjuste`. Adjustments feed the Zero-Sum equation and must bring it to exactly
zero before the reconciliation can be committed.

**Why this priority**: Adjustments are how real-world discrepancies are formally resolved,
so the books can close at exactly zero.

**Independent Test**: Can be fully tested against an existing `Conciliacion` with a known
residual difference by adding adjustments and confirming the equation reaches zero and
commits.

**Acceptance Scenarios**:

1. **Given** a `Conciliacion` with a residual difference, **When** the operator adds an
   `AjusteConciliacion` with a `ConceptoAjuste`, **Then** the adjusted totals satisfy the
   Zero-Sum equation and the reconciliation commits.
2. **Given** an adjustment that does not bring the equation to exactly zero, **When**
   committing, **Then** the transaction is rolled back.

---

### User Story 4 - Trace every imported record to its batch (Priority: P4)

Every financial record (`MovimientoBancario`, `MovimientoInterno`) is traceable to a
`LoteImportacion` (import batch) that records its source and timestamp.

**Why this priority**: Auditability requires every imported figure to be attributable to a
specific import event, preventing untraceable or duplicated data.

**Independent Test**: Can be fully tested by importing a batch and verifying every resulting
movement references the same `LoteImportacion`.

**Acceptance Scenarios**:

1. **Given** an import is executed, **When** records are created, **Then** each
   `MovimientoBancario` and `MovimientoInterno` is linked to exactly one `LoteImportacion`
   with its source and timestamp.
2. **Given** an import of a `LoteImportacion` that was already imported, **When** the system
   processes it again, **Then** the duplicate import is rejected to avoid double-counting.

---

### User Story 5 - Revert to unlock reconciled records (Priority: P5)

Reconciled records are locked against direct editing. The operator must revert the parent
`Conciliacion` to unlock them for correction.

**Why this priority**: Partial immutability protects the integrity of a closed
reconciliation while still allowing corrections through a controlled, auditable path.

**Independent Test**: Can be fully tested by attempting to edit a reconciled record (expect
rejection) and then reverting the `Conciliacion` (expect records become editable).

**Acceptance Scenarios**:

1. **Given** a committed `Conciliacion`, **When** the operator attempts to directly edit a
   reconciled detail or movement, **Then** the system rejects the edit.
2. **Given** a committed `Conciliacion`, **When** the operator reverts it, **Then** the
   affected records are unlocked and the reconciliation returns to a draft/open state.

---

### User Story 6 - Flag bank movements "En Consulta" (Priority: P6)

The administrator flags a `MovimientoBancario` as "En Consulta" (under investigation) to
visually isolate deposits that are waiting on the sales department's receipts. The flag does
not remove the movement from the pending list; it only marks it for focused follow-up.

**Why this priority**: Real-world reconciliations stall on deposits whose supporting receipts
are missing; isolating them prevents them from being overlooked while keeping them visible.

**Independent Test**: Can be fully tested by flagging one or more pending bank movements and
verifying they remain in the pending list while appearing in the "En Consulta" isolate view.

**Acceptance Scenarios**:

1. **Given** a pending `MovimientoBancario`, **When** an administrator flags it as "En
   Consulta", **Then** the movement remains in the pending list and is visually marked and
   isolated as under investigation.
2. **Given** a movement flagged "En Consulta", **When** the administrator clears the flag,
   **Then** the movement returns to its normal pending state without any data loss.

---

### User Story 7 - Leave quick annotations on movements (Priority: P7)

Users can attach a short free-text note to any `MovimientoBancario` or `MovimientoInterno` as
a digital "post-it", capturing working context without changing the financial record itself.

**Why this priority**: Operators need lightweight, in-place context (e.g., "awaiting invoice
1234") that does not alter amounts, dates, or reconciliation state.

**Independent Test**: Can be fully tested by adding, editing, and clearing a note on a
movement and verifying the note persists independently of reconciliation status.

**Acceptance Scenarios**:

1. **Given** a `MovimientoBancario` or `MovimientoInterno`, **When** the user saves a text
   note, **Then** the note is persisted and displayed with the record.
2. **Given** a record with an existing note, **When** the user edits or clears the note,
   **Then** the change is saved without affecting the record's amount, date, or
   reconciliation state.

---

### User Story 8 - Match with extreme date tolerance (Priority: P8)

The matching logic is mathematically ruthless with amounts — matches require exact cent-level
equality per the currency's precision — but completely permissive with dates. Users may match
records whose dates are weeks apart; the UI may surface a warning, but the action must never
be blocked.

**Why this priority**: Amount exactness protects the Zero-Sum invariant, while date
flexibility reflects real-world practice where a deposit and its internal counterpart are
posted far apart.

**Independent Test**: Can be fully tested by matching a bank movement to an internal movement
with widely separated dates (identical amounts) and confirming the match succeeds with an
optional warning, while a one-cent amount difference still fails.

**Acceptance Scenarios**:

1. **Given** two movements with identical amounts but dates weeks apart, **When** the user
   matches them, **Then** the match succeeds (the UI may warn about the date gap but does not
   block the action).
2. **Given** two movements whose amounts differ by one cent, **When** the user attempts to
   match them, **Then** the match is rejected because amounts must be exact.

---

### User Story 9 - Hybrid UX: split-screen and printable report (Priority: P9)

The reconciliation UI provides a split-screen digital matching interface (bank side and
internal side side-by-side) AND a printer-friendly "Manual Checking Report" view that uses CSS
print media queries to hide sidebars and backgrounds for clean paper output.

**Why this priority**: Operators reconcile efficiently on screen, while auditors and the sales
department need a paper-friendly report for manual checking and receipt follow-up.

**Independent Test**: Can be fully tested by rendering both views from the same data and
verifying the split-screen presents both sides simultaneously and the print view hides
non-essential UI elements.

**Acceptance Scenarios**:

1. **Given** a reconciliation in progress, **When** the operator opens the matching view,
   **Then** bank and internal movements are displayed side-by-side in a split-screen layout.
2. **Given** the "Manual Checking Report" view, **When** it is rendered for printing, **Then**
   CSS print media queries hide sidebars and backgrounds, producing a printer-friendly layout.

---

### Edge Cases

- Zero-Sum violated by a single cent → the entire reconciliation transaction must roll back.
- Monetary amounts with more decimal places than the currency's `cantidad_decimales` →
  rejected or rounded deterministically per the currency precision, never via floating point.
- Duplicate import of the same `LoteImportacion` → rejected to avoid double-counting.
- Reverting an already-reverted or never-committed `Conciliacion` → rejected with an
  informative error.
- Currency mismatch between a bank movement and its account → blocked or flagged.
- Zero-amount movements or adjustments → handled without breaking the Zero-Sum equation.
- Reconciliation with no movements → valid; Zero-Sum is trivially zero.
- Matching records with extreme date gaps (weeks apart) → allowed; the UI shows a warning but
  never blocks the action.
- A movement flagged "En Consulta" that is subsequently matched or reconciled → the flag does
  not interfere with matching or Zero-Sum enforcement.
- Notes on a movement → treated as display-only metadata; they never participate in matching,
  amounts, or the Zero-Sum equation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain master catalogs `Banco`, `TipoCuenta`, `Moneda`,
  `TipoOperacion`, and `ConceptoAjuste`, each with stable unique codes and descriptive
  labels.
- **FR-002**: `Moneda` MUST include `cantidad_decimales`, defining the exact decimal
  precision for amounts in that currency.
- **FR-003**: System MUST record financial accounts and movements (`CuentaBancaria`,
  `MovimientoBancario`, `MovimientoInterno`).
- **FR-004**: Every `MovimientoBancario` and `MovimientoInterno` MUST be associated with
  exactly one `LoteImportacion` for traceability.
- **FR-005**: System MUST allow creating a `Conciliacion` header that groups
  `DetalleConciliacionBancaria` and `DetalleConciliacionInterna` entries.
- **FR-006**: The core service layer MUST enforce the Zero-Sum equation
  `Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0` before committing any reconciliation;
  if it is not strictly zero, the entire transaction MUST roll back.
- **FR-007**: All financial arithmetic MUST use exact decimal arithmetic (Python's
  `decimal.Decimal`); floating-point arithmetic is prohibited for monetary values.
- **FR-008**: System MUST support `AjusteConciliacion` entries classified by
  `ConceptoAjuste` to resolve differences.
- **FR-009**: System MUST persist monetary amounts using the precision defined by the
  associated `Moneda.cantidad_decimales`.
- **FR-010**: Reconciled records MUST be partially immutable: direct edits are rejected, and
  only reverting the parent `Conciliacion` unlocks them for editing.
- **FR-011**: System MUST provide custom wrappers that resolve absolute paths via
  `sys._MEIPASS` for SQLite and static assets, preparing the application for single Windows
  `.exe` compilation.
- **FR-012**: System MUST reject duplicate imports of the same `LoteImportacion`.
- **FR-013**: System MUST allow administrators to flag a `MovimientoBancario` as "En Consulta"
  (under investigation) to visually isolate it while it remains in the pending list.
- **FR-014**: System MUST provide a free-text `notas` (notes) field on both
  `MovimientoBancario` and `MovimientoInterno`; notes are display-only metadata and MUST NOT
  affect amounts, matching, or Zero-Sum enforcement.
- **FR-015**: Matching MUST be exact on amounts to the currency's precision (the cent) and
  permissive on dates; records with dates weeks apart MAY be matched, and the UI MAY warn
  about a date gap but MUST never block the action.
- **FR-016**: System MUST provide a split-screen digital matching interface showing bank and
  internal movements side-by-side.
- **FR-017**: System MUST provide a printer-friendly "Manual Checking Report" view that uses
  CSS print media queries to hide sidebars and backgrounds.

### Key Entities *(include if feature involves data)*

- **Banco**: Catalog of banks; identified by a unique code and name.
- **TipoCuenta**: Catalog of account types (e.g., checking, savings).
- **Moneda**: Catalog of currencies; MUST include `cantidad_decimales` (decimal precision).
- **TipoOperacion**: Catalog of operation types used to classify movements.
- **ConceptoAjuste**: Catalog of adjustment concepts used to classify `AjusteConciliacion`.
- **LoteImportacion**: Import batch for traceability; records source and timestamp and
  groups all movements from a single import.
- **CuentaBancaria**: A bank account; linked to `Banco`, `TipoCuenta`, and `Moneda`.
- **MovimientoBancario**: A bank-side movement; linked to `CuentaBancaria`,
  `LoteImportacion`, `TipoOperacion`, and `Moneda`; includes a free-text `notas` (notes)
  field and an "En Consulta" (under investigation) flag.
- **MovimientoInterno**: An internal movement; linked to `LoteImportacion`,
  `TipoOperacion`, and `Moneda`; includes a free-text `notas` (notes) field.
- **Conciliacion**: Reconciliation header; holds state (draft/committed/reverted), the date
  range, and account scope.
- **DetalleConciliacionBancaria**: Bank-side detail line belonging to a `Conciliacion`.
- **DetalleConciliacionInterna**: Internal-side detail line belonging to a `Conciliacion`.
- **AjusteConciliacion**: Adjustment line belonging to a `Conciliacion`; linked to a
  `ConceptoAjuste`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of reconciliation commits whose totals do not satisfy the Zero-Sum
  equation are rejected and fully rolled back, with no partial data persisted.
- **SC-002**: 100% of monetary calculations preserve exact decimal precision with no
  floating-point rounding across all currencies and `cantidad_decimales`.
- **SC-003**: Reconciled records cannot be modified by any direct edit; unlocking requires
  reverting the parent `Conciliacion` (verified end-to-end).
- **SC-004**: 100% of imported financial records are traceable to a `LoteImportacion`.
- **SC-005**: The application builds into a single Windows `.exe` that resolves SQLite and
  static assets correctly on a clean machine via `sys._MEIPASS` wrappers.
- **SC-006**: Accuracy and data integrity are prioritized over execution speed, matching the
  single-enterprise internal audience.
- **SC-007**: 100% of amount-based matches are exact to the currency's precision, while a
  date-gap warning is surfaced (but never blocks) for records spanning weeks apart.
- **SC-008**: The split-screen matching view and the printer-friendly "Manual Checking Report"
  render correctly, with CSS print media queries hiding sidebars and backgrounds.

## Assumptions

- Single-enterprise internal deployment (no multi-tenancy); correctness and data integrity
  are prioritized over raw performance.
- SQLite is the desktop database, packaged within a single Windows `.exe`.
- Backend uses Django 5.1+ (per the project constitution).
- Frontend uses Tailwind CSS + Alpine.js v3 (per the project constitution).
- Monetary values are stored and calculated in exact decimal per `Moneda.cantidad_decimales`.
- Entity and field identifiers and UI strings are in Spanish; specification and architectural
  documentation are in English (per the project constitution).
- Target platform is Windows 10/11 for the compiled executable.

