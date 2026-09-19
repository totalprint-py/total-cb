# Feature Specification: Conciliación Bancaria (Extracto y Punteo)

**Feature Branch**: `004-conciliacion-bancaria`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Feature 004 — 'Conciliación Bancaria (Extracto y Punteo)' for SENDA S.A. Ingest the bank
statement (extracto) into a new `MovimientoExtracto` model via bulk Excel/CSV import and manual CRUD; provide a
unified punteo UI to match it against the internal `MovimientoLibro`; enable an on-the-fly 'Create Book Entry'
action from a statement row; and strictly lock a `MovimientoLibro` once matched."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest the bank statement (extracto) (Priority: P1)

A finance operator loads a bank statement into the system using either a bulk upload of an Excel (`.xlsx`) or CSV
file, or the manual CRUD form for quick fixes. Every row becomes a `MovimientoExtracto` record bound to a selected
`CuentaBancaria`. The operator can later edit or delete a statement row while it remains unmatched.

**Why this priority**: No matching can happen until statement data exists. Ingestion is the foundation the punteo
and adjustment flows depend on.

**Independent Test**: Fully testable by uploading/creating `MovimientoExtracto` rows against a known
`CuentaBancaria` and asserting the persisted rows and their fields — with no matching involved.

**Acceptance Scenarios**:

1. **Given** a `.xlsx` file whose rows map to the import column contract, **When** the operator uploads it for a
   chosen account, **Then** every valid row is persisted as a `MovimientoExtracto` (all-or-nothing: any invalid row
   rolls back the whole import and reports each row error in Spanish).
2. **Given** a `.csv` file with the same contract, **When** uploaded, **Then** it is parsed identically to the
   `.xlsx` path and persisted with the same all-or-nothing rule.
3. **Given** the manual form, **When** the operator enters `fecha`, `referencia` (optional), `detalle` and a non-zero
   `importe`, **Then** a new `MovimientoExtracto` is created; editing it before matching updates the same fields.

---

### User Story 2 - Punteo: match extracto against libro (Priority: P1)

Using a unified, side-by-side (dual-list) screen, the operator selects an unmatched `MovimientoExtracto` on one side
and an unmatched `MovimientoLibro` of the same account on the other, and links them. Matching establishes the
"Conciliado" status on both sides.

**Why this priority**: This is the core of the feature's name ("Punteo") and the activity that drives the ledger
toward a reconciled state.

**Independent Test**: Fully testable against seeded unmatched `MovimientoExtracto` and `MovimientoLibro` rows by
selecting a matching pair and asserting both records flip to `conciliado` and the link (`Punteo`) is persisted — with
no import or book-entry creation involved.

**Acceptance Scenarios**:

1. **Given** an account with unmatched extracto and libro rows of equal amount, **When** the operator selects a
   matching pair and submits, **Then** a `Punteo` link is created and both records become `conciliado`.
2. **Given** a selected pair whose amounts differ, **When** the operator submits, **Then** no link is created and a
   Spanish error message is shown (HTTP 400).
3. **Given** a record already `conciliado`, **When** the punteo screen renders, **Then** that record is excluded from
   the unmatched lists.

---

### User Story 3 - Create a book entry from a statement row (Priority: P2)

When the statement contains an item missing from the internal books (e.g., bank fees or taxes), the operator triggers
a "Create Book Entry" quick action directly from the `MovimientoExtracto` row. The system creates the corresponding
`MovimientoLibro` row and links it back to the statement row, marking both `conciliado`.

**Why this priority**: It closes the reconciliation loop for statement-only items and keeps the internal book aligned
with the bank, but it is secondary to the basic ingestion + matching flow.

**Independent Test**: Fully testable by invoking the action on a single unmatched `MovimientoExtracto` and asserting
the created `MovimientoLibro` (correct `debe`/`haber` sign mapping, recomputed running `saldo`) is immediately linked
via `Punteo` — with no punteo selection step required.

**Acceptance Scenarios**:

1. **Given** an unmatched `MovimientoExtracto` whose signed amount has no counterpart in the libro, **When** the
   operator triggers "Create Book Entry", **Then** a `MovimientoLibro` is created on the same account with the amount
   mapped to the correct `debe`/`haber` side and its `saldo` recomputed chronologically, then both records are linked
   and marked `conciliado`.

---

### User Story 4 - Lock matched (conciliado) records (Priority: P1)

A `MovimientoLibro` (and, symmetrically, its `MovimientoExtracto`) that has been matched (`conciliado`) is strictly
locked: while `conciliado`, both sides of the `Punteo` are locked against edit and delete through any surface (model
`delete`, update view, delete view, and the library template's action buttons), protecting the reconciliation from
being broken. The controlled, auditable un-match `despuntear` is the ONLY release: it resets both `conciliado` flags
and removes the link, after which the records become editable again.

**Why this priority**: Financial integrity is non-negotiable; an unlocked conciliated record would silently break the
punteo invariant established in User Story 2/3. Locking therefore requires an intentional, audited release.

**Independent Test**: Fully testable by marking a `MovimientoLibro` `conciliado` and asserting every edit/delete
surface (model `delete`, update view, delete view) raises a typed protection error, and that only `despuntear` releases it.

**Acceptance Scenarios**:

1. **Given** a `conciliado` `MovimientoLibro` (and its linked `MovimientoExtracto`), **When** any edit or delete
   operation is attempted, **Then** it is rejected with a Spanish error and the records are unchanged.
2. **Given** a linked pair, **When** the operator invokes the audited `despuntear` un-match, **Then** both records
   return to unmatched (`conciliado = False`), the `Punteo` link is removed, and the records become editable again —
   this is the only way to release a locked record.

---

### Edge Cases

- What happens when the uploaded file has a missing header, an empty row, or an unknown column? → rejected with a row
  error; nothing persisted.
- What happens when a statement `importe` is zero, or is a `float`/non-numeric string? → rejected (`ImporteDecimalField`
  rejects `float`; zero violates a `CheckConstraint`).
- What happens when an `importe` decodes to more precision than the account's 2-decimal currency? → rounded with
  `ROUND_HALF_EVEN` via the existing `quantize_to_moneda` boundary.
- What happens when both lists are empty for an account? → the punteo screen shows empty-state messages.
- What happens when the operator selects a pair from different accounts? → rejected (matching is scoped to one account).
- What happens when a "Create Book Entry" is attempted on an already-matched extracto? → rejected (no double booking).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a new `MovimientoExtracto` model tied to a `CuentaBancaria` with `fecha`,
  `referencia` (optional), `detalle`, and a signed `importe` (non-zero), plus an `origen` provenance
  (`manual` | `importacion`) and a `conciliado` flag.
- **FR-002**: System MUST import `.xlsx` (openpyxl) and `.csv` (stdlib `csv`) files into `MovimientoExtracto` in a
  single all-or-nothing transaction; any invalid row rolls back the whole import and returns that row's error(s).
- **FR-003**: System MUST provide standard CRUD (list/create/update/delete) for `MovimientoExtracto` for manual entry
  and quick fixes, reusing the existing Spanish-label form conventions.
- **FR-004**: System MUST provide a unified, side-by-side punteo screen (Alpine.js v3 + offline Bootstrap 5) listing
  unmatched `MovimientoExtracto` against unmatched `MovimientoLibro` for a selected account, with select-and-submit
  linking.
- **FR-005**: System MUST link a `MovimientoExtracto` to a `MovimientoLibro` only when their amounts match by EXACT
  `decimal.Decimal` equality (no ± cent tolerance): `extracto.importe == libro.debe - libro.haber` after
  `quantize_to_moneda` at 2 decimal places (`ROUND_HALF_EVEN`).
- **FR-006**: System MUST enforce STRICT 1:1 pairing: each `MovimientoExtracto` and each `MovimientoLibro` is unique
  on both sides of a `Punteo` (via `UniqueConstraint` on each foreign key), so 1:N and N:N grouping are impossible.
- **FR-007**: A successful link MUST set `conciliado = True` on both records and persist a `Punteo` link record
  atomically. While `conciliado`, both records are locked against edit/delete (FR-009), so the ONLY release is the
  controlled, auditable un-match `despuntear`, which MUST reset both flags and remove the link; every match/un-match
  transition is recorded for audit.
- **FR-008**: System MUST provide a "Create Book Entry" quick action that creates a `MovimientoLibro` from a
  `MovimientoExtracto` row (correct `debe`/`haber` sign mapping), recomputes the running `saldo` chronologically, and
  links/marks both records `conciliado` in one transaction.
- **FR-009**: System MUST strictly lock a `conciliado` `MovimientoLibro` against edit and delete at every surface
  (model `delete`, update view, delete view, and the library template's action buttons), returning a typed domain error.
- **FR-010**: All monetary values MUST use `Decimal` (`ImporteDecimalField`, 2 decimal places), never `float`; domain
  constraints MUST be declared with `CheckConstraint(condition=Q(...))` and uniqueness with `UniqueConstraint`.
- **FR-011**: All UI strings and database identifiers MUST be in Spanish; the specification and documentation remain in
  English (project constitution, Principle 0).

### Key Entities *(include if feature involves data)*

- **MovimientoExtracto** (new): one bank-statement line for a `CuentaBancaria`; `fecha`, `referencia`, `detalle`,
  signed `importe` (2 dp), `origen`, `conciliado`.
- **Punteo** (new): the link record pairing exactly one `MovimientoExtracto` with exactly one `MovimientoLibro`
  (unique on both sides).
- **AuditoriaPunteo** (new): append-only audit record of every match/un-match transition
  (`fecha_hora`, `accion` = `puntear`|`despuntear`, references to both sides of the Punteo,
  and the acting principal/user).
- **MovimientoLibro** (existing, hardened): the internal ledger line (`cuenta`, `fecha`, `tipo_operacion`, `detalle`,
  `debe`, `haber`, derived `saldo`, `conciliado`); gains lock-on-match semantics per FR-009.
- **CuentaBancaria** (existing): the reconcilable account; reused with no schema change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of imports either persist every valid row or roll back the entire transaction, with per-row errors.
- **SC-002**: 100% of successful links match amounts to the cent with no floating-point drift, and set both records
  `conciliado`.
- **SC-003**: 0 `conciliado` `MovimientoLibro` records are editable or deletable via any surface.
- **SC-004**: "Create Book Entry" produces a `MovimientoLibro` whose `saldo` equals the chronological running balance
  `saldo_base + debe - haber`, exact to the cent.
- **SC-005**: An operator can match (or create-then-match) a statement item in 3 interactions or fewer.

## Assumptions

- **COEXISTENCE**: Feature 004 is a new, independent "Extracto & Punteo" module that coexists with the existing 001
  engine (`MovimientoBancario` ↔ `MovimientoInterno` in `matcher.html`); it introduces its own entities
  (`MovimientoExtracto`, `Punteo`) and does NOT replace, extend, or modify the 001 engine, which remains untouched and
  fully operational.
- The signed-amount convention for `MovimientoExtracto.importe` mirrors the implemented `MovimientoLibro` rule
  `saldo = saldo_base + debe - haber`: the statement `importe` equals the libro's net `debe - haber` (positive =
  money in / `debe`; negative = money out / `haber`).
- No new third-party dependencies are required: `openpyxl` and stdlib `csv` are already available.
- While matched, the `MovimientoExtracto` side is locked symmetrically with its `MovimientoLibro` (both require an
  explicit `despuntear` to release), avoiding a dangling one-sided link.
- `tipo_operacion` on a book entry created "on the fly" is resolved deterministically via
  `TipoOperacion.objects.get_or_create(codigo='AJUSTE-BANCARIO', defaults={'nombre': 'Ajuste Bancario'})`
  (single canonical default; documented in data-model.md).
