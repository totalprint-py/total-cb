# Data Model: Reportes del Libro Bancario (Bank Ledger Reports)

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16

Read-only reporting model. **No new persistent entities and no migrations**: the report is a derived,
in-memory projection of the existing `MovimientoLibro` / `CuentaBancaria` schema. Money is
`decimal.Decimal` (never `float`); identifiers and UI strings are Spanish (Principle 0).

## Reused entities (read-only sources)

| Entity | Fields used | Relationship | Notes |
|---|---|---|---|
| `CuentaBancaria` | `banco`, `tipo_cuenta`, `moneda`, `numero_cuenta`, `denominacion`, `saldo_inicial` | FK → `Banco`, `TipoCuenta`, `Moneda` | Selected account; `saldo_inicial` used only when the range has no prior movements |
| `MovimientoLibro` | `fecha`, `tipo_operacion`, `detalle`, `debe`, `haber`, `saldo` (`editable=False`) | FK → `CuentaBancaria` (CASCADE), FK → `TipoOperacion` (PROTECT) | `Meta.ordering = ["fecha", "id"]`; `saldo` already stores the running balance |

## Derived (non-persistent) result type — `ReporteLibro`

| Field | Type | Meaning |
|---|---|---|
| `cuenta` | `CuentaBancaria` | the selected account |
| `fecha_desde` / `fecha_hasta` | `date` | inclusive report boundaries |
| `movimientos` | `list[MovimientoLibro]` | in-range rows, ordered `fecha` then `id` |
| `saldo_inicial_periodo` | `Decimal` | opening balance of the range (FR-004) |
| `total_debe` | `Decimal` | `sum(debe)` over `movimientos` |
| `total_haber` | `Decimal` | `sum(haber)` over `movimientos` |
| `saldo_final` | `Decimal` (computed) | `saldo_inicial_periodo + total_debe - total_haber` |

## Derivation rules

1. **Filter** (FR-002): `MovimientoLibro.objects.filter(cuenta=cuenta, fecha__gte=fecha_desde,
   fecha__lte=fecha_hasta).order_by("fecha", "id")`.
2. **Opening balance** (FR-004): the `saldo` of the latest `MovimientoLibro` with `fecha < fecha_desde`
   for the same `cuenta`; if none exists, `cuenta.saldo_inicial`.
3. **Totals** (FR-005): `total_debe = sum(m.debe)`, `total_haber = sum(m.haber)` over the filtered rows;
   for an empty range either sum is `Decimal("0.00")`.
4. **Closing balance** (FR-005): `saldo_final = saldo_inicial_periodo + total_debe - total_haber`.
   This must equal the last in-range row's `saldo` (or the opening balance when the range is empty),
   matching the engine convention `saldo = saldo_base + debe - haber`.

## Validation rules (from spec FRs)

- FR-001/FR-008: `fecha_desde` and `fecha_hasta` are required valid dates and `fecha_desde <= fecha_hasta`;
  otherwise raise the domain error `RangoFechasInvalidoError` (surfaced as 400 / Spanish message).
- FR-010: every monetary value is computed with `decimal.Decimal` and displayed with 2 decimal places.
- FR-009: all paths are read-only — no `create`/`update`/`delete` on any entity.
