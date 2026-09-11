# Service Layer Contracts: Core Reconciliation Engine

**Branch**: `001-core-reconciliation-engine` | **Date**: 2026-09-04

Domain boundary for `conciliacion/services.py`. Views MUST call these functions and MUST NOT
re-implement their logic. Monetary parameters accept only `decimal.Decimal`.

## Conventions

- Pure functions: no HTTP/request access; inputs are plain values/objects; persistence happens
  only inside the transactional orchestrators.
- Money: `decimal.Decimal` only — any `float` raises `TypeError` (see `assert_decimal`).
- Errors: typed domain exceptions (`ZeroSumError`, `AmountMismatchError`, `EstadoInvalidoError`).

## Contracts

### `assert_decimal(value) -> Decimal`
- Pre: `value` is `int`, `str`, or `Decimal`.
- Post: returns `Decimal(value)`.
- Error: `TypeError` if `value` is `float` (float rejected at the boundary).

### `flag_en_consulta(*, movimiento_bancario, en_consulta: bool) -> None`
- Pre: `movimiento_bancario` exists.
- Post: `en_consulta` set; movement remains in the pending list (FR-013).

### `set_nota(*, movimiento, texto: str) -> None`
- Pre: `movimiento` is `MovimientoBancario` or `MovimientoInterno`.
- Post: `notas` updated; no amount/date/state change (FR-014).

### `match_movimientos(*, bancario, interno) -> tuple[DetalleConciliacionBancaria, DetalleConciliacionInterna]`
- Pre: amounts are `Decimal`; both movements exist and are not already matched.
- Post: creates the matched detail pair when amounts are exactly equal (FR-015).
- Error: `AmountMismatchError` if amounts differ (even by one cent).
- Warning: surfaces a non-blocking `DateGapWarning` if dates differ beyond a threshold (never
  raises/blocking).

### `commit_reconciliation(*, conciliacion) -> None`  [@transaction.atomic]
- Pre: `conciliacion.estado == draft`.
- Post: if `Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0` exactly, state → `committed`.
- Error: `ZeroSumError` → atomic rollback of everything (FR-006, SC-001).

### `create_ajuste(*, conciliacion, concepto_ajuste, importe: Decimal) -> AjusteConciliacion`
- Pre: `importe` is `Decimal`; `conciliacion` is draft.
- Post: adjustment persisted; feeds the Zero-Sum equation (FR-008).

### `revert_conciliacion(*, conciliacion) -> None`  [@transaction.atomic]
- Pre: `conciliacion.estado == committed`.
- Post: state → `reverted`/draft; linked records unlocked for editing (FR-010).
- Error: `EstadoInvalidoError` if already reverted or never committed.
