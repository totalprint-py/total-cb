# Implementation Plan: Conciliación Bancaria (Extracto y Punteo)

**Branch**: `004-conciliacion-bancaria` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-conciliacion-bancaria/spec.md`

## Summary

Add the "Extracto & Punteo" surface over the validated **Libro Bancario** ledger. A new `MovimientoExtracto` model
holds bank-statement lines ingested by bulk Excel/CSV import or by a standard CRUD form. A new Alpine.js/Bootstrap
dual-list "punteo" screen pairs unmatched `MovimientoExtracto` rows against unmatched `MovimientoLibro` rows of the
same account, persisting a 1:1 `Punteo` link that flips both sides to `conciliado`. A "Create Book Entry" quick action
materializes a book entry from a statement-only row and links it immediately. Matched `MovimientoLibro` rows become
strictly locked (no edit/delete). All arithmetic is `Decimal` and all matches are exact to the cent.

## Technical Context

**Language/Version**: Python 3.14 (Django 6.0.7; `requirements.txt` pins `Django>=5.1,<7.0`)

**Primary Dependencies**: Django, offline Bootstrap 5, Alpine.js v3, PyInstaller; reuses `openpyxl` (XLSX import) and
stdlib `csv` (CSV import) — no new third-party dependencies

**Storage**: SQLite (single `.db` via `totalcb/paths.py`); new migration for `MovimientoExtracto` + `Punteo`

**Testing**: pytest + pytest-django (TDD Red-Green-Refactor)

**Target Platform**: Windows 10/11 (compiled single `.exe` via PyInstaller + pywebview)

**Project Type**: Desktop web application (local Django app, frozen with PyInstaller)

**Performance Goals**: Correctness over speed (single internal user); sub-second import/match for hundreds of rows

**Constraints**: Offline; no client-side build step; `Decimal` arithmetic (2 dp); Spanish locale; PyInstaller-safe
(pure-Python) dependencies; strict immutability of `conciliado` records

**Scale/Scope**: 3 new models, 1 migration, 1 import module, 1 punteo service module, ~8 views/URLs, 3 templates,
~5 test modules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle 0 — Language Strictness (CRITICAL)**: PASS — docs/plan in English; identifiers/UI in Spanish
  (`MovimientoExtracto`, `Punteo`, `conciliado`, "Punteo", "Conciliación Bancaria").
- **Principle 1 — Database Integrity**: PASS — new `CheckConstraint(condition=Q(...))` on `MovimientoExtracto`
  (`importe != 0`, `origen__in=["manual","importacion"]`) and `UniqueConstraint` on both sides of `Punteo`; no legacy
  `check=` argument anywhere.
- **Principle 2 — Integrated Frontend**: PASS — offline Bootstrap 5 + Alpine.js v3 dual-list; no build step
  (constitution v2.0.0 mandates Bootstrap 5 with the Alpine.js amendment).
- **Principle 3 — TDD**: PASS — failing tests first for import services, punteo service, views, and the immutability
  guards.
- **Principle 4 — Desktop Readiness**: PASS — `openpyxl`/`csv` are pure Python; the upload path reads the uploaded
  stream in memory and writes no scratch files (PyInstaller/frozen-safe); assets via `{% static %}`.
- **Principle 5 — Financial Precision & Zero-Sum**: PASS — all money is `Decimal`, locked at 2 dp via
  `quantize_to_moneda`; each `Punteo` enforces exact per-pair equality
  (`extracto.importe == libro.debe - libro.haber`), so no value is created or destroyed. **Exact-equality rule (FR-005):**
  the comparison happens **after** both operands are `quantize_to_moneda`'d to exactly **2 decimal places** with
  `ROUND_HALF_EVEN`, using `Decimal` equality only — **no `float`, no ±cent tolerance**. With both sides locked to 2 dp,
  a plain `Decimal` `==` is a purely integer-pennies comparison and cannot drift.

*Post-design re-check*: PASS; no violations.

## Architectural Components

### 1. Models (new) — `conciliacion/models.py`

- `MovimientoExtracto`: `cuenta_bancaria` (FK PROTECT), `fecha`, `referencia` (blank), `detalle`, `importe`
  (`ImporteDecimalField`, 18/2), `origen` (`manual`|`importacion`), `conciliado` (bool). Constraints: non-zero
  `importe`, valid `origen`. Meta `ordering = ["fecha","id"]`.
- `Punteo`: `movimiento_extracto` (FK, `related_name="punteo"`), `movimiento_libro` (FK, `related_name="punteo"`).
  `UniqueConstraint` on each FK column (strict 1:1).
- `AuditoriaPunteo`: `fecha_hora` (auto_now_add), `accion` (`puntear`|`despuntear`), FKs PROTECT to both sides,
  `usuario`; `CheckConstraint(condition=Q(accion__in=["puntear","despuntear"]))`; append-only audit trail per FR-007.

### 2. Import module (new, pure) — `conciliacion/importadores.py`

Parses `.xlsx` (openpyxl) and `.csv` (stdlib) against the column contract (`contracts/import-format.md`) into a list
of candidate rows; raises per-row errors (missing header, invalid/empty `importe`, non-`Decimal`, bad date). The
transactional persist + rollback lives in the punteo/import service layer.

**Bank sign convention (pinned from the benchmark fixture `1 Continental Guaranies.xlsx`, sheet `CONTINENTAL`):**
The real export uses two columns (not the canonical single `importe`) with this header: `FECHA, OPERACIÓN, DETALLE,
DEBE, HABER, SALDO`. Sampled rows show `DEBE` holds money-in (`Deposito BELLINI` → 980,000) and `HABER` holds
money-out (`EGRESO COMPRA $ 20,000*6.010` → 120,200,000); the running `SALDO` follows `SALDO = SALDO_prev + DEBE -
HABER`. Therefore `importe = DEBE - HABER` reproduces the canonical signed amount (positive = money in, negative =
money out) with **no sign inversion** relative to `MovimientoLibro` (`saldo = saldo_base + debe - haber`): bank `DEBE`
≡ `MovimientoLibro.debe` (money in) and bank `HABER` ≡ `MovimientoLibro.haber` (money out). The parser normalizes this
layout to the canonical `importe` before punteo and additionally: (1) matches headers case-insensitively; (2) ignores
the extra `OPERACIÓN` and `SALDO` columns; (3) skips the `Saldo Anterior` preamble row (opening balance booked under
`HABER`) and the footer totals row (`DEBE=207,500,227`, `HABER=199,405,356`, `SALDO=8,094,871`) so no phantom movement
is imported. See `contracts/import-format.md`.

### 3. Punteo service (new) — `conciliacion/punteo.py`

- Typed errors: `ImporteNoCoincideError`, `ConciliadoBloqueadoError`, `EstadoInvalidoError`.
- `importar_extracto(cuenta, archivo, formato)` — parse + `transaction.atomic` bulk-create, all-or-nothing.
- `puntear(*, extracto, libro)` — validates same-account + exact amount (**both sides `quantize_to_moneda` to 2 dp
  first, then strict `Decimal` equality, no `float`/no tolerance**), creates `Punteo`, flips both flags `conciliado`,
  writes an `AuditoriaPunteo` row (accion=`puntear`).
- `despuntear(*, extracto)` — removes the link, resets both flags, and writes an `AuditoriaPunteo` row
  (accion=`despuntear`) in the same `transaction.atomic` block (audited release per FR-007).
- `crear_asiento_desde_extracto(*, extracto)` — maps the sign to `debe`/`haber`, creates `MovimientoLibro`, recomputes
  running `saldo` (reuse `MovimientoLibro.recalcular_saldos`), then links and marks `conciliado` in one transaction.

### 4. Views + URLs (new) — `conciliacion/views.py` / `urls.py`

- CBVs: `extracto_list`, `extracto_create`, `extracto_update`, `extracto_delete` (locked once matched).
- Function views: `extracto_importar` (GET form + POST), `punteo` (GET dual-list), `puntear` (POST match; 400 on
  domain error), `despuntear` (POST), `crear_asiento_extracto` (GET form + POST).

### 5. Forms + templates (new) — `conciliacion/forms.py`, `templates/conciliacion/`

- `MovimientoExtractoForm`, `ExtractoImportarForm` (cuenta + archivo).
- `extracto_list.html`, `extracto_form.html`, `extracto_importar.html`, `punteo.html`
  (Alpine.js `x-data="punteador()"` dual-list, mirrors `matcher.html`), `crear_asiento_form.html`.
- `libro_bancario.html`: hide/disable Edit/Delete on `conciliado` rows (lock indicator).

### 6. Sidebar integration — `templates/base.html`

Add "Extracto Bancario" and "Punteo" nav entries consistent with the existing sidebar.

### 7. Tests — `tests/unit/`

`test_extracto_modelos.py`, `test_extracto_importadores.py`, `test_extracto_servicios.py`,
`test_extracto_vistas.py`, `test_punteo_templates.py` (+ extend `test_movimiento_libro.py` for the lock guard).

## Project Structure

### Documentation (this feature)

```text
specs/004-conciliacion-bancaria/
├── plan.md              # this file (/speckit-plan output)
├── research.md          # Phase 0 output — resolved decisions
├── data-model.md        # Phase 1 output — entities, fields, constraints, state
├── quickstart.md        # Phase 1 output — runnable validation guide
├── contracts/
│   ├── http-api.md      # endpoints, params, status codes
│   └── import-format.md # column contract + validation + error model
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
conciliacion/            # Django app
├── models.py            # + MovimientoExtracto, Punteo (MovimientoLibro hardened)
├── forms.py             # + MovimientoExtractoForm, ExtractoImportarForm
├── importadores.py      # NEW: xlsx/csv parser (pure)
├── punteo.py            # NEW: import/match/unmatch/create-asiento + immutability guards
├── views.py             # + extracto CRUD + punteo/import/create-asiento views
├── urls.py              # + extracto_*, punteo/puntear/despuntear, crear_asiento_extracto
├── migrations/          # + 0008_movimientoextracto_punteo_auditoria
├── templates/conciliacion/
│   ├── extracto_list.html
│   ├── extracto_form.html
│   ├── extracto_importar.html
│   ├── punteo.html
│   └── crear_asiento_form.html
└── (libro_bancario.html updated with lock indicators)

templates/base.html      # + "Extracto Bancario" and "Punteo" sidebar entries

tests/unit/              # + test_extracto_* and test_punteo_* (TDD)
```

**Structure Decision**: Single Django project + single `conciliacion` app (single-enterprise desktop scope). Statement
parsing and punteo orchestration live in dedicated modules (`importadores.py`, `punteo.py`) so views stay thin and the
001 engine's `services.py` is untouched — mirroring the 003 decision to keep report aggregation in `reportes.py`.
