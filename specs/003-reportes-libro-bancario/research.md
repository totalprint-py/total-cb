# Research: Reportes del Libro Bancario (Bank Ledger Reports)

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16

Phase 0 findings resolving all technical unknowns. Format: Decision / Rationale / Alternatives considered.

## R1. PDF generation library

- **Decision**: Use **fpdf2** (`fpdf`, pure Python).
- **Rationale**: A single, small dependency with no C or native extensions, so it bundles cleanly into the
  single-file Windows `.exe` (Constitution Principle 4). It is sufficient for a tabular ledger with a
  header and a totals footer, which is all this report needs.
- **Alternatives considered**: (a) reportlab — larger footprint and more features than required;
  (b) weasyprint — requires native Cairo/Pango, a packaging risk on Windows + PyInstaller;
  (c) xhtml2pdf — heavy transitive dependencies and imperfect CSS. All rejected for this scope.

## R2. Spreadsheet exports (Excel/CSV)

- **Decision**: Excel `.xlsx` via **openpyxl**; CSV via the **standard library `csv`** (UTF-8 with BOM).
- **Rationale**: openpyxl is the de-facto pure-Python `.xlsx` writer and is PyInstaller-friendly; CSV
  needs no dependency and acts as a zero-footprint fallback. Both render the same aggregated
  `ReporteLibro`, so the "identical data across formats" requirement (FR-007) holds by construction.
- **Alternatives considered**: pandas/XlsxWriter (overkill), xlwt (legacy `.xls`), odfpy. Rejected.

## R3. "Saldo inicial" (opening balance) semantics

- **Decision**: The report opening balance is the `saldo` of the latest `MovimientoLibro` with
  `fecha < fecha_desde`, or the account's `saldo_inicial` when no such movement exists (spec FR-004).
- **Rationale**: This is the only convention that makes the footer reconcile: the closing balance
  equals the last in-range row's stored `saldo`, and `saldo_final = saldo_inicial_periodo + total_debe
  - total_haber`. It is correct for a mid-ledger range and degrades gracefully to `saldo_inicial` for
  the first range.
- **Alternatives considered**: (a) always use `saldo_inicial` — wrong for any range that starts after
  movements already exist; (b) reconstruct a virtual opening by summing history — redundant, since each
  row's stored `saldo` already encodes the history.

## R4. Authoritative balance convention

- **Decision**: Follow the already-validated engine convention `saldo = saldo_base + debe - haber`
  (`debe` increases an asset account, `haber` decreases it), as implemented in
  `MovimientoLibro.save()` and `MovimientoLibro.recalcular_saldos()`.
- **Rationale**: The engine is the source of truth; the report must mirror it exactly so the footer
  totals match the running balances shown on screen (`saldo_final = saldo_inicial_periodo + total_debe
  - total_haber`).
- **Alternatives considered**: none — the implemented engine wins over any differently-worded prose.

## R5. Number formatting per output

- **Decision**: HTML and PDF render human-readable strings using the configured Spanish locale
  (comma decimal, dot thousands — `settings.DECIMAL_SEPARATOR`, `THOUSAND_SEPARATOR`). CSV emits
  semicolon-delimited, decimal-comma values (Spanish Excel convention) with a UTF-8 BOM. XLSX writes
  native numeric cells with a 2-decimal display format.
- **Rationale**: On-screen/PDF target humans and follow the application locale; CSV/XLSX target
  accounting re-use, where numeric cells remain summable and comma decimals match regional Excel.
- **Alternatives considered**: dot-decimal everywhere (confusing for Spanish users); text cells in XLSX
  (not summable). Rejected.

## R6. Aggregation & rendering placement (read-only)

- **Decision**: Put the pure aggregation in a new `conciliacion/reportes.py` (a `ReporteLibro` result
  type, a `RangoFechasInvalidoError`, and a `generar_reporte_libro()` function), and the file renderers
  in `conciliacion/exportadores.py` (CSV/XLSX/PDF bytes). Views remain thin HTTP adapters.
- **Rationale**: One aggregation consumed by all four outputs guarantees FR-007 (identical data) and
  FR-009 (read-only) by construction, and mirrors the existing 001 `services.py` "business logic out of
  views" pattern. Reports are projections, not a `MovimientoLibro`/`CuentaBancaria` responsibility.
- **Alternatives considered**: (a) logic duplicated in each view — drift risk across formats;
  (b) model-method aggregation — mixes a derived projection into the entity. Rejected.

## R7. File delivery & desktop packaging

- **Decision**: Stream bytes via `HttpResponse` with `Content-Disposition: attachment; filename=...` and
  the correct MIME type; write no files to disk.
- **Rationale**: The desktop host (embedded browser) natively handles attachment downloads, avoiding
  temp-file lifecycle issues under a frozen PyInstaller working directory.
- **Alternatives considered**: writing files to `data_dir()` then redirecting — extra state and cleanup
  risk. Rejected.
