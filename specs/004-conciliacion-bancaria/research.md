# Research & Decisions — Conciliación Bancaria (Extracto y Punteo)

Phase 0 output. Each entry resolves an open question or a default chosen from the spec, with rationale and rejected
alternatives.

## R1 — Import technology (XLSX + CSV)

- **Decision**: Parse `.xlsx` with the existing `openpyxl` dependency and `.csv` with the standard-library `csv` module;
  no new dependencies are added.
- **Rationale**: Both are pure Python and already PyInstaller-safe; `openpyxl` is already bundled for 003 exports.
- **Alternatives considered**: `pandas` (rejected — heavy, native-wheel complexity under PyInstaller); `xlrd`
  (rejected — legacy `.xls` only and less maintained).

## R2 — Statement amount convention

- **Decision**: `MovimientoExtracto.importe` is a single signed `Decimal` (2 dp) whose sign mirrors the implemented
  `MovimientoLibro` rule `saldo = saldo_base + debe - haber`; the matching invariant is
  `extracto.importe == libro.debe - libro.haber`.
- **Rationale**: A single signed column is what real bank exports contain and keeps the punteo match a single equality;
  it is consistent with the existing ledger code (verified in `conciliacion/models.py`).
- **Alternatives considered**: mirroring the libro's two-column `debe`/`haber` on the extracto (rejected — cheaper to
  derive the signed amount at import and keep matching trivially correct).

## R3 — Match rule and cardinality

- **Decision**: Strict 1:1 pairing enforced by `UniqueConstraint` on both sides of `Punteo`; amounts must match exactly
  after `quantize_to_moneda` (2 dp) — no tolerance.
- **Rationale**: Per-pair exact equality is the strongest form of the Constitution's zero-sum principle; 1:1 mirrors the
  existing 001 `match_movimientos` pairwise model and keeps the lock semantics unambiguous.
- **Alternatives considered**: tolerance matching (rejected by default; flagged as a spec clarification) and 1:N
  grouping (rejected by default; flagged as a spec clarification).

## R4 — Immutability enforcement

- **Decision**: Three layers: (1) `MovimientoLibro.delete()` raises `ConciliadoBloqueadoError` when `conciliado`; (2)
  the update and delete views re-validate the flag and return a Spanish error; (3) the template hides/disables the
  edit/delete buttons. The `MovimientoExtracto` side is locked symmetrically and released only by `despuntear`.
- **Rationale**: A financial lock must hold regardless of which surface is used; the DB `on_delete=PROTECT` on `Punteo`
  provides a fourth, defensive layer against raw ORM deletion of a linked row.
- **Alternatives considered**: relying solely on form validation (rejected — bypassable via ORM/shell); removing the
  edit/delete URLs entirely (rejected — breaks the ability to fix unmatched data).

## R5 — Scope relationship to the 001 engine

- **Decision (default, pending PO confirmation)**: Feature 004 is a new, independent "Extracto & Punteo" module that
  coexists with the existing 001 engine (`MovimientoBancario` ↔ `MovimientoInterno` on `matcher.html`); it introduces
  its own entities (`MovimientoExtracto`, `Punteo`) and does not modify the 001 engine.
- **Rationale**: The PO's directive explicitly names a new `MovimientoExtracto` model and a `MovimientoLibro` matching
  surface — distinct from `MovimientoBancario`/`MovimientoInterno`.
- **Alternatives considered**: repurposing/extending `MovimientoBancario` as the statement source (rejected by the PO's
  explicit model name and the need to not destabilize a validated engine).

## R6 — "Create Book Entry" tier

- **Decision**: The action creates the `MovimientoLibro` (auto-assigning a default `tipo_operacion` such as "Ajuste",
  resolved in data-model), recomputes the account's running `saldo` via `MovimientoLibro.recalcular_saldos`, then
  auto-links the new row to the source `MovimientoExtracto` (both `conciliado`) in a single transaction.
- **Rationale**: By construction the sign-mapped amount equals the statement amount, so auto-linking is safe and is the
  "quick" single-interaction behavior the directive implies.
- **Alternatives considered**: create-without-link then manual punteo (rejected — extra interaction, no safety gain).
