# Feature Specification: Libro Bancario (Bank Ledger)

**Feature Branch**: `002-libro-bancario`

**Created**: 2026-09-09

**Status**: Converged

**Input**: User description: "Add a high-speed 'Libro Bancario' module within the Django conciliacion application. The module allows selecting a specific bank account (linking Banco, TipoCuenta, and Moneda), viewing its chronological ledger movements, and entering new transactions via an optimized horizontal data-entry form. Each transaction automatically calculates and updates the running balance based on the previous movement or initial account balance."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Select an account and view its ledger (Priority: P1)

The finance operator opens the "Libro Bancario" module and selects a specific bank account. The
selection surface reflects the account's linked `Banco`, `TipoCuenta`, and `Moneda` (for example,
showing the bank name, account type, and currency alongside the account). Once selected, the module
lists that account's ledger movements (`MovimientoLibro`) in strict chronological order (`fecha`,
then `id`), with each row showing its computed running balance.

**Why this priority**: Reading the ledger is the primary reason the module exists. Without a
correct, chronologically-ordered view with a running balance, the operator cannot trust the book.

**Independent Test**: Can be fully tested by creating an account with a known set of `MovimientoLibro`
records and rendering the selection + list, verifying ordering and running-balance values with no
data-entry flow involved.

**Acceptance Scenarios**:

1. **Given** an account with several ledger movements across different dates, **When** the operator
   selects that account, **Then** the movements are rendered ordered by `fecha` (ties broken by
   `id`), and each row displays a running balance equal to the cumulative `saldo_base - debe +
   haber`.
2. **Given** an account with no movements, **When** the operator selects it, **Then** the ledger
   renders empty and the account's `saldo_inicial` is shown as the starting balance.
3. **Given** multiple accounts, **When** the operator selects a different account, **Then** the
   ledger switches to that account's movements and the shown `Banco`, `TipoCuenta`, and `Moneda`
   update accordingly.

---

### User Story 2 - Enter a transaction via the horizontal form (Priority: P2)

The operator enters a new ledger transaction using a single-row, optimized horizontal form with the
fields `fecha`, `tipo_operacion`, `detalle`, `debe`, and `haber`. Submitting persists the movement
and automatically computes its running balance from the previous chronological movement's balance
or, for the first movement, from the account's `saldo_inicial`.

**Why this priority**: Data entry is the second core activity. A horizontal, minimal-click form
minimizes the operator's effort and error rate when keying many transactions quickly.

**Independent Test**: Can be fully tested by submitting a movement against an account with a known
previous balance and verifying the persisted `saldo` without needing the reconciliation engine or
any catalog UI.

**Acceptance Scenarios**:

1. **Given** an account whose last chronological movement has balance `B`, **When** a new movement
   is submitted with `debe = D` and `haber = H`, **Then** the persisted movement has
   `saldo = B - D + H`.
2. **Given** an account with no prior movements and `saldo_inicial = S`, **When** the first movement
   is submitted, **Then** the persisted movement has `saldo = S - D + H`.
3. **Given** the form is submitted with invalid data (e.g., a negative `debe` or a missing
   `tipo_operacion`), **When** the operator attempts to save, **Then** the movement is not
   persisted and inline validation errors are shown.

---

### User Story 3 - Keep the running balance consistent (Priority: P3)

When balances become inconsistent — for example, after a backdated or corrected entry — the operator
can recalculate the entire running balance for the selected account. The system rebuilds every
movement's `saldo` from the account's `saldo_inicial` in chronological order and persists the
corrected values.

**Why this priority**: The running balance is only trustworthy if it can always be repaired
deterministically. This is a safety net rather than a daily task, so it is lower priority than
viewing and entry.

**Independent Test**: Can be fully tested by corrupting stored `saldo` values directly (bypassing the
balance logic) and invoking the recalculation, then verifying every `saldo` is restored.

**Acceptance Scenarios**:

1. **Given** movements whose stored `saldo` values are out of sync, **When** recalculation runs for
   the account, **Then** each movement's `saldo` is recomputed as `saldo_base - debe + haber`
   starting from `saldo_inicial`, in `fecha`/`id` order, and persisted.
2. **Given** a fully consistent ledger, **When** recalculation runs, **Then** the balances are
   unchanged (idempotent).

---

### Edge Cases

- **Empty ledger**: the first movement of an account must base its balance on `saldo_inicial`.
- **Backdated entry** (a new movement whose `fecha` is earlier than the latest existing movement):
  its balance is computed from the chronologically latest movement's balance; later-dated movements
  become stale until `recalcular_saldos` is run. This behavior must be documented and detectable.
- **Both `debe` and `haber` zero**: the balance is unchanged; the entry should be flagged as
  invalid (at least one of `debe`/`haber` must be non-zero).
- **Negative `debe` or `haber`**: must be rejected (amounts are non-negative magnitudes).
- **Deleting a referenced account**: deleting a `CuentaBancaria` removes its `MovimientoLibro`
  records (CASCADE). Deleting a `TipoOperacion` still referenced by movements must be blocked
  (PROTECT).
- **Monetary precision**: all amounts and balances use exact decimal arithmetic at 2 decimal places;
  `float` is never used.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow the operator to select a specific `CuentaBancaria` and MUST display
  its linked `Banco`, `TipoCuenta`, and `Moneda`.
- **FR-002**: System MUST list the selected account's `MovimientoLibro` records ordered by `fecha`
  ascending, with ties broken by `id` ascending.
- **FR-003**: System MUST display a running-balance column on every ledger row.
- **FR-004**: System MUST provide a horizontal, single-row data-entry form with the fields `fecha`,
  `tipo_operacion`, `detalle`, `debe`, and `haber`.
- **FR-005**: On creation, the system MUST compute the movement's `saldo` as
  `saldo = saldo_base - debe + haber`, where `saldo_base` is the chronologically latest existing
  movement's `saldo`, or the account's `saldo_inicial` when no movements exist.
- **FR-006**: The system MUST NOT allow the `saldo` field to be edited by the user; it is derived
  exclusively from the balance engine.
- **FR-007**: The system MUST reject negative `debe`/`haber` and require at least one of them to be
  non-zero.
- **FR-008**: The system MUST provide a recalculation operation that rebuilds every `saldo` for an
  account from `saldo_inicial` in chronological order.
- **FR-009**: All monetary values MUST use `decimal.Decimal` (never `float`) with 2-decimal-place
  precision.
- **FR-010**: `tipo_operacion` MUST be protected against deletion while referenced by a movement
  (`PROTECT`); deleting a `CuentaBancaria` MUST cascade to its movements.
- **FR-011**: All UI strings MUST be in Spanish; database identifiers MUST be in Spanish; the
  specification and documentation MUST be in English (per the project constitution).

### Key Entities *(include if feature involves data)*

- **MovimientoLibro**: A single ledger line for a `CuentaBancaria`. Holds `fecha`,
  `tipo_operacion` (FK, PROTECT), `detalle`, `debe`, `haber`, the derived `saldo`, and a
  `conciliado` flag. Ordered by `fecha`, `id`.
- **CuentaBancaria**: The selected account; links `Banco`, `TipoCuenta`, and `Moneda`, and holds
  `saldo_inicial` (the starting balance used for the first movement).
- **Banco / TipoCuenta / Moneda**: Reference catalogs shown with the selected account to give the
  operator context.
- **TipoOperacion**: Reference catalog used to classify each ledger movement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of persisted movements have a `saldo` equal to `saldo_base - debe + haber`
  (exact to the cent, no floating-point drift).
- **SC-002**: The operator can enter a new transaction with a single submission from one horizontal
  form row, without navigating away from the ledger.
- **SC-003**: The ledger renders all movements in `fecha`/`id` order with a correct running balance
  for any selected account.
- **SC-004**: Recalculation restores 100% of corrupted `saldo` values to the correct running
  balance, and is idempotent on an already-consistent ledger.
- **SC-005**: The module reuses the existing application shell (sidebar navigation, Alpine.js) and
  requires no new client-side build step or external service.

## Assumptions

- Single-enterprise internal desktop deployment (SQLite, single Windows `.exe`), matching the
  existing application.
- The module reuses the existing application shell (`templates/base.html` sidebar + Alpine.js v3)
  and the form-styling conventions already used by the catalog CRUD screens (`conciliacion/forms.py`).
- The `MovimientoLibro` model, `MovimientoLibroForm`, and initial unit tests already exist from
  earlier work; this feature completes the presentation layer (views, URLs, templates), validation,
  and end-to-end coverage.
- The `CuentaBancaria`, `Banco`, `TipoCuenta`, `Moneda`, and `TipoOperacion` catalogs already exist
  and are reused as-is (no new catalog entities are introduced).
- The balance convention is `saldo = saldo_base - debe + haber` (a `debe` reduces the balance, a
  `haber` increases it), consistent with the already-implemented model.


