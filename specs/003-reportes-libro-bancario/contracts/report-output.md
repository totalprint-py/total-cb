# Contract: Reportes del Libro Bancario — Canonical report output

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16

This is the single canonical report structure that every output (HTML, CSV, Excel, PDF) MUST represent
identically (FR-007). Sources of truth: [data-model.md](../data-model.md) for the derived fields and
`conciliacion/reportes.py` for the aggregation.

## Layout & columns

| # | Column | Source | Notes |
|---|---|---|---|
| 1 | `Fecha` | `MovimientoLibro.fecha` | locale `d/m/Y` in human outputs; ISO `YYYY-MM-DD` in CSV |
| 2 | `Tipo` | `MovimientoLibro.tipo_operacion` | short name |
| 3 | `Detalle` | `MovimientoLibro.detalle` | free text |
| 4 | `Debe` | `MovimientoLibro.debe` | 2 dp |
| 5 | `Haber` | `MovimientoLibro.haber` | 2 dp |
| 6 | `Saldo` | `MovimientoLibro.saldo` | running balance, 2 dp |

Ordering: ascending `fecha`, then `id` (the model's `Meta.ordering`), unchanged across formats.

## Footer (totals block)

Rendered after the detail rows, in this order and with these Spanish labels:

- `Saldo inicial` = `reporte.saldo_inicial_periodo` (opening balance of the range; FR-004).
- `Total Debe` = `reporte.total_debe` (`sum(debe)` over the range).
- `Total Haber` = `reporte.total_haber` (`sum(haber)` over the range).
- `Saldo final` = `reporte.saldo_final` = `saldo_inicial_periodo + total_debe - total_haber` (FR-005).

Invariant: `Saldo final` MUST equal the `saldo` of the last detail row (or the `Saldo inicial` itself
when the range is empty).

## Human vs machine representation

| Output | Value encoding |
|---|---|
| HTML | locale strings: comma decimal, dot thousands (per `settings`); `</span>` no editable inputs |
| PDF | same locale strings as HTML, rendered by fpdf2 |
| CSV | semicolon delimiter, decimal-comma, UTF-8 BOM, no thousands separator |
| XLSX | native numeric cells, 2-decimal display format (summable), header + footer rows |

## Empty-range behavior

When `movimientos` is empty, every output still shows the header, `Saldo inicial`, zero totals
(`0,00`) in `Total Debe` / `Total Haber`, and `Saldo final = Saldo inicial`; in the HTML a single
"Sin movimientos en el rango seleccionado." row occupies the detail area.
