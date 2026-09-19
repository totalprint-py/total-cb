# Quickstart & Validation — Conciliación Bancaria (Extracto y Punteo)

Runnable validation scenarios that prove the feature end-to-end. No implementation code is reproduced here; see
`contracts/` and `data-model.md` for the precise shapes.

## Prerequisites

- Windows + Python (project uses 3.14), `pip install -r requirements.txt`.
- `cd c:\python\total-cb` (all commands run from the repo root).

## 1. Migrate + seed

```powershell
python manage.py makemigrations conciliacion   # creates the MovimientoExtracto + Punteo + AuditoriaPunteo migration
python manage.py migrate
python -m pytest -q                           # full suite stays green (TDD baseline)
```

## 2. Import (bulk) — TDD contract

- Create a `CuentaBancaria` (or use a seeded one) and a sample `.csv`/`.xlsx` with the header row
  `fecha,referencia,detalle,importe` (see `contracts/import-format.md`).
- `python -m pytest tests/unit/test_extracto_importadores.py` — assert happy-path persistence, all-or-nothing rollback
  on a bad row, zero/`float` amount rejection, missing-header rejection.

## 3. Manual CRUD

- Visit `/extracto/` (`extracto_list`), create/edit a row via the form; confirm Spanish labels and that matched rows are
  read-only after punteo.
- `python -m pytest tests/unit/test_extracto_vistas.py` — assert status codes/redirects and lock behavior on matched rows.

## 4. Punteo (match)

- Visit `/punteo/`, select a same-amount `MovimientoExtracto` + `MovimientoLibro`, submit `puntear`.
- Assert both rows show `conciliado` and disappear from the unmatched lists; assert a mismatched pair returns 400 and
  nothing is persisted.
- `python -m pytest tests/unit/test_extracto_servicios.py` — covers `puntear`, `despuntear`, mismatch error, uniquity.

## 5. Create Book Entry

- On an unmatched statement-only row, trigger "Create Book Entry"; assert a `MovimientoLibro` is created with the
  correct `debe`/`haber` mapping, the account's running `saldo` is recomputed, and both records are linked/`conciliado`.
- Covered by `test_extracto_servicios.py::test_crear_asiento_desde_extracto_*`.

## 6. Immutability

- Attempt to edit/delete a `conciliado` `MovimientoLibro` via the UI and via the model `delete()`; assert a Spanish
  error and unchanged data. Covered by the `ConciliadoBloqueadoError` tests.

## 7. Desktop smoke (regression)

- Rebuild with `build.ps1` and launch `dist\SENDA_Bancario\SENDA_Bancario.exe`; confirm the new sidebar entries load in
  the kiosk window and that the bundled DB + import flow work offline.
