# Data Model: Core Reconciliation Engine

**Branch**: `001-core-reconciliation-engine` | **Date**: 2026-09-04

Physical model for the Django app `conciliacion`. Monetary fields are `DecimalField` (never
`FloatField`); domain constraints use `CheckConstraint(condition=Q(...))`. Identifiers are in
Spanish (Principle 0).

## Catalog entities

| Entity | Fields | Constraints |
|---|---|---|
| `Banco` | `codigo` (CharField, unique), `nombre` | `codigo` unique, required |
| `TipoCuenta` | `codigo` (unique), `nombre` | `codigo` unique, required |
| `Moneda` | `codigo` (unique), `nombre`, `cantidad_decimales` (PositiveIntegerField) | `cantidad_decimales >= 0` (CheckConstraint) |
| `TipoOperacion` | `codigo` (unique), `nombre` | `codigo` unique, required |
| `ConceptoAjuste` | `codigo` (unique), `nombre` | `codigo` unique, required |

## Operational entities

| Entity | Fields | Relationships | Constraints |
|---|---|---|---|
| `LoteImportacion` | `fuente`, `fecha_importacion` | — | unique import identity (dedupe, FR-012) |
| `CuentaBancaria` | `numero`, `nombre` | FK → `Banco`, `TipoCuenta`, `Moneda` | currency must match its `Moneda` |
| `MovimientoBancario` | `importe` (DecimalField), `fecha`, `notas` (optional TextField), `en_consulta` (Boolean, default False) | FK → `CuentaBancaria`, `LoteImportacion`, `TipoOperacion`, `Moneda` | amount precision per `Moneda`; `en_consulta` keeps it pending (FR-013) |
| `MovimientoInterno` | `importe` (DecimalField), `fecha`, `notas` (optional TextField) | FK → `LoteImportacion`, `TipoOperacion`, `Moneda` | amount precision per `Moneda` |
| `Conciliacion` | `estado` (draft/committed/reverted), `fecha_desde`, `fecha_hasta` | FK → `CuentaBancaria` | state transitions below |
| `DetalleConciliacionBancaria` | — | FK → `Conciliacion`, `MovimientoBancario` | one movement per conciliacion (unique pair) |
| `DetalleConciliacionInterna` | — | FK → `Conciliacion`, `MovimientoInterno` | one movement per conciliacion (unique pair) |
| `AjusteConciliacion` | `importe` (DecimalField) | FK → `Conciliacion`, `ConceptoAjuste` | feeds Zero-Sum equation |

## Notes & flags

- `notas` on both movement types is display-only metadata: it MUST NOT participate in matching,
  arithmetic, or the Zero-Sum equation (FR-014).
- `en_consulta` ("En Consulta") on `MovimientoBancario` is a visual-isolation flag; it does NOT
  remove the movement from the pending list (FR-013).

## State transitions

- `Conciliacion.estado`: `draft` → `committed` (Zero-Sum holds) → `reverted` (unlocks records)
  → `draft` (reopenable). A committed conciliacion's details/movements are locked (FR-010).
- `MovimientoBancario.en_consulta`: `False` ↔ `True`; independent of reconciliation state.

## Validation rules (from spec FRs)

- FR-002 / US2: `Moneda.cantidad_decimales` required, non-negative integer.
- FR-009: amounts quantized to `cantidad_decimales` via `Decimal.quantize`.
- FR-004 / SC-004: every movement links to exactly one `LoteImportacion`.
- FR-006 / SC-001: Zero-Sum `Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0` before commit.
- FR-012: duplicate `LoteImportacion` import rejected.
