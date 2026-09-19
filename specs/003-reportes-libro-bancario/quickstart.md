# Quickstart: Reportes del Libro Bancario (Bank Ledger Reports)

**Branch**: `003-reportes-libro-bancario` | **Date**: 2026-09-16

Runnable validation scenarios proving the feature end-to-end. See
[data-model.md](./data-model.md), [contracts/http-api.md](./contracts/http-api.md), and
[contracts/report-output.md](./contracts/report-output.md) for details.

## Prerequisites

- Windows 10/11 with Python 3.14 and a virtualenv at `venv/`.
- Dependencies installed (now includes the two new exports libraries):

```powershell
venv\Scripts\pip install -r requirements.txt
```

- Django project configured with SQLite (absolute path) and `conciliacion` in `INSTALLED_APPS`.

## Setup

```powershell
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py runserver
```

## Automated tests (TDD gate)

```powershell
venv\Scripts\python.exe -m pytest -q
```

Expected: existing engine tests plus the new `tests/unit/test_reportes_libro.py` cases pass, covering:
range filtering, opening-balance selection (latest prior `saldo` vs `saldo_inicial`), `total_debe` /
`total_haber` / `saldo_final`, empty range, invalid range (`desde > hasta`), and the CSV/XLSX/PDF
exporters and the four report views (status codes + `Content-Disposition`).

## Manual scenario (UI)

1. Seed catalogs (`Bancos`, `Tipos de Cuenta`, `Monedas`, `Tipos de Operación`) and a `CuentaBancaria`
   with `saldo_inicial` (e.g. `1000.00`) using the existing CRUD screens.
2. Load several `MovimientoLibro` rows across multiple dates via **Libro Bancario** (e.g. Debe `250.00`
   on day 1, Haber `100.00` on day 2, Debe `500.00` on day 3; running balances `1250.00`, `1150.00`,
   `1650.00`).
3. Open **Reportes Bancarios** from the sidebar, select the account, and set `desde`/`hasta` to cover
   days 2–3 only.
   - Expected (HTML): rows for day 2 and day 3 only, in `fecha`/`id` order; footer `Saldo inicial =
     1250,00`, `Total Debe = 500,00`, `Total Haber = 100,00`, `Saldo final = 1650,00`.
4. Press **Imprimir** (uses `window.print()`); verify the filter bar is hidden (`no-print`) and the
   table + totals print cleanly.
5. Download each export and verify:
   - **CSV**: semicolon-delimited, decimal-comma, header + footer rows, same numbers as HTML.
   - **Excel**: `.xlsx` with numeric cells; summing `Debe`/`Haber` reproduces the totals.
   - **PDF**: a table with the same rows and the `Saldo inicial` / `Total Debe` / `Total Haber` /
     `Saldo final` footer.
6. Edge cases:
   - Range with no movements → empty detail ("Sin movimientos…") but footer `Saldo inicial =
     Saldo final`, totals `0,00`.
   - `desde > hasta` → inline Spanish error, and the export endpoints return 400 with no file.
   - Range starting before the first movement → `Saldo inicial = saldo_inicial` of the account.

## Notes

- No new migrations: the report is a read-only projection of `MovimientoLibro` / `CuentaBancaria`.
- `fpdf` and `openpyxl` are the only new runtime dependencies; both are pure Python and PyInstaller-safe.
- Exports stream bytes directly (no files written to disk), matching desktop download behavior.
