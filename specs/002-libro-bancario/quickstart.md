# Quickstart: Libro Bancario (Bank Ledger)

**Branch**: `002-libro-bancario` | **Date**: 2026-09-10

Runnable validation scenarios proving the feature end-to-end. See
[data-model.md](./data-model.md) and [contracts/http-api.md](./contracts/http-api.md) for details.

## Prerequisites

- Windows 10/11 with Python 3.14 and a virtualenv at `venv/`.
- Dependencies installed: `venv\Scripts\pip install -r requirements.txt`.
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

Expected: existing `MovimientoLibro` engine tests plus the new `test_libro_bancario.py` cases pass,
covering FR-007 validation (negative `debe`/`haber` rejected; both-zero rejected), the Master-Detail
view context, movement-creation redirect, and the recalculation endpoint.

## Manual scenario (UI)

1. Seed catalogs via the existing CRUD screens (`Bancos`, `Tipos de Cuenta`, `Monedas`,
   `Tipos de Operación`) or the Django shell.
2. Create a `CuentaBancaria` with `saldo_inicial` (e.g. `1000.00`).
3. Open **Libro Bancario** from the sidebar and select the account.
   - Expected: the page shows the account's `Banco`, `TipoCuenta`, `Moneda`, and an empty ledger with
     `saldo_inicial` as the starting balance.
4. With keyboard: focus lands on `fecha` (autofocus); `Tab` through `fecha` → `tipo_operacion` →
   `detalle` → `debe` → `haber`; type a movement (e.g. `debe=250.00`) and press `Enter`.
   - Expected: a new row appears with `saldo = 750.00`; the form clears and stays on the account.
5. Add a `haber` movement (e.g. `100.00`) on a later date and submit.
   - Expected: new row `saldo = 850.00`.
6. Try invalid input: negative `debe`, or both `debe`/`haber` = 0.
   - Expected: the row is not persisted and inline Spanish errors appear.
7. Run "Recalcular saldos".
   - Expected: balances are recomputed in `fecha`/`id` order from `saldo_inicial` and are unchanged on
     an already-consistent ledger (idempotent).

## Notes

- No new migration beyond the FR-007 `CheckConstraint` (`0005_*`); the ledger table schema already
  exists from migration `0004_movimientolibro`.
- No client-side build step: `bootstrap.min.css` and `alpine.min.js` are already collected/static.
