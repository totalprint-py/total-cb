# Data Model: Libro Bancario (Bank Ledger)

**Branch**: `002-libro-bancario` | **Date**: 2026-09-10

Physical model for the `conciliacion` app. `MovimientoLibro` and `CuentaBancaria` already exist and
are reused; this feature adds the FR-007 validation constraints and the presentation layer. Money is
`DecimalField` (never `FloatField`); identifiers are Spanish (Principle 0).

## Reused entities (already implemented)

| Entity | Fields | Relationships | Constraints |
|---|---|---|---|
| `CuentaBancaria` | `banco` (FK), `tipo_cuenta` (FK), `moneda` (FK), `numero_cuenta` (CharField 50), `denominacion` (CharField 100), `saldo_inicial` (DecimalField 18,2, default 0.00) | FK → `Banco`, `TipoCuenta`, `Moneda` (all CASCADE) | — |
| `MovimientoLibro` | `cuenta` (FK), `fecha` (DateField), `tipo_operacion` (FK), `detalle` (CharField 255), `debe` (DecimalField 18,2, default 0.00), `haber` (DecimalField 18,2, default 0.00), `saldo` (DecimalField 18,2, default 0.00, `editable=False`), `conciliado` (BooleanField, default False) | FK → `CuentaBancaria` (CASCADE), FK → `TipoOperacion` (PROTECT) | `Meta.ordering = ["fecha", "id"]` |

## New constraints for this feature (FR-007)

| Constraint name | Condition (`Q(...)`) | Purpose |
|---|---|---|
| `movimiento_libro_debe_no_negativo` | `Q(debe__gte=0)` | reject negative `debe` |
| `movimiento_libro_haber_no_negativo` | `Q(haber__gte=0)` | reject negative `haber` |
| `movimiento_libro_importe_requerido` | `Q(debe__gt=0) | Q(haber__gt=0)` | require at least one non-zero |

These are added to `MovimientoLibro.Meta.constraints` using `CheckConstraint(condition=Q(...))`
(Principle 1). A corresponding migration (`0005_*`) applies them; `MovimientoLibro.clean()` and
`MovimientoLibroForm.clean()` mirror the same rules to surface Spanish inline validation errors.

## Running-balance derivation (FR-005, FR-006)

- On insert (`self.pk is None`), `saldo_base` is:
  - the `saldo` of the chronologically-latest `MovimientoLibro` for the same `cuenta` (ordered
    `fecha`, `id`), or
  - `cuenta.saldo_inicial` when no movement exists.
- Derived value: `saldo = saldo_base - debe + haber`.
- `saldo` is `editable=False` (FR-006); the UI never renders an editable `saldo` input.
- Backdated-entry caveat: a new row whose `fecha` precedes the latest row is computed from the latest
  row and can leave later-dated rows stale until `MovimientoLibro.recalcular_saldos(cuenta_id)` runs
  (FR-008).

## Relationships / deletion rules (FR-010)

- Deleting a `CuentaBancaria` cascades to its `MovimientoLibro` rows (`on_delete=CASCADE`).
- Deleting a `TipoOperacion` referenced by any movement is blocked (`on_delete=PROTECT`).

## Validation rules (from spec FRs)

- FR-007: `debe >= 0`, `haber >= 0`, and `debe > 0 OR haber > 0`.
- FR-009: all monetary values use `decimal.Decimal` with 2 decimal places.
- FR-011: identifiers/UI in Spanish; docs in English.
