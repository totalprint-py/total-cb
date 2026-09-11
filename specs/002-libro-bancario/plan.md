# Implementation Plan: Libro Bancario (Bank Ledger)

**Branch**: `002-libro-bancario` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-libro-bancario/spec.md`

## Summary

Complete the presentation layer for the **Libro Bancario** module over the already-implemented
`MovimientoLibro` running-balance engine. The operator selects a `CuentaBancaria` (the UI shows its
linked `Banco`, `TipoCuenta`, and `Moneda`), views the account's `MovimientoLibro` rows in strict
`fecha`/`id` order with a running-balance column, and enters new movements through a single-row,
horizontal, keyboard-first form. The balance engine already lives in `MovimientoLibro.save()`
(`saldo = saldo_base - debe + haber`; the first movement bases off `CuentaBancaria.saldo_inicial`).
This feature adds the FR-007 validation guard, the high-contrast Master-Detail template, thin views,
URLs, a recalculation action wired to `MovimientoLibro.recalcular_saldos`, and end-to-end tests.

## Technical Context

**Language/Version**: Python 3.14 (Django 5.1+; `requirements.txt` pins `Django>=5.1,<7.0`, installed 6.0.x)

**Primary Dependencies**: Django, offline Bootstrap 5 (`static/css/bootstrap.min.css`), Alpine.js v3 (`static/js/alpine.min.js`), PyInstaller

**Storage**: SQLite (single `.db`, absolute path via `totalcb/paths.py` → `database_path()`)

**Testing**: pytest + pytest-django (TDD Red-Green-Refactor)

**Target Platform**: Windows 10/11 (compiled single `.exe`)

**Project Type**: Desktop web application (local Django app, frozen with PyInstaller)

**Performance Goals**: Correctness over speed (single internal user); sub-second ledger render for thousands of rows

**Constraints**: Offline; no client-side build step; exact `decimal.Decimal` arithmetic (2 dp); keyboard-first data entry (Tab/Enter); high-contrast Master-Detail layout

**Scale/Scope**: 5 existing catalogs + `CuentaBancaria` + `MovimientoLibro`; one new UX surface (account selector + ledger + horizontal entry form + recalculation)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle 0 — Language Strictness (CRITICAL)**: PASS — docs/plan in English; identifiers and UI strings in Spanish (`MovimientoLibro`, `CuentaBancaria`, `saldo`, "Libro Bancario").
- **Principle 1 — Database Integrity**: PASS — the new FR-007 guard uses `CheckConstraint(condition=Q(...))` (e.g. `debe__gte=0`, `haber__gte=0`, `Q(debe__gt=0) | Q(haber__gt=0)`); no legacy `check=`.
- **Principle 2 — Integrated Frontend**: **VIOLATION (justified)** — the constitution mandates "Tailwind CSS + Alpine.js v3", but this feature, per explicit product-owner direction, uses **offline Bootstrap 5** (`bootstrap.min.css`) with Alpine.js v3 for reactivity. The existing application shell (`templates/base.html`) and catalog forms (`conciliacion/forms.py`) already use Bootstrap 5 (`form-control`, `form-select`, `card`, `table`). Tracked in Complexity Tracking; requires a constitution amendment (Principle 2 → "Bootstrap 5 + Alpine.js v3") or an approved waiver.
- **Principle 3 — TDD**: PASS — failing tests first for FR-007 validation, the Master-Detail view, and the recalculation endpoint.
- **Principle 4 — Desktop Readiness**: PASS — assets via `{% static %}` (`bootstrap.min.css`, `alpine.min.js`); SQLite via absolute `paths.database_path()`; no new build step.
- **Principle 5 — Financial Precision & Zero-Sum**: PASS — `debe`/`haber`/`saldo`/`saldo_inicial` are `DecimalField(max_digits=18, decimal_places=2)`; the running-balance engine and `recalcular_saldos` use `decimal.Decimal` only.

*Post-design re-check*: PASS with the single tracked Principle 2 deviation (see Complexity Tracking); all other gates hold.

## Architectural Components

### 1. Running-balance engine (existing, in `MovimientoLibro.save()`)

`MovimientoLibro.save()` computes `saldo` only on insert (`self.pk is None`): it reads the
chronologically-latest existing movement for the same `cuenta` (ordered `fecha`, `id`) and uses its
`saldo` as `saldo_base`; when none exists it uses `cuenta.saldo_inicial`. Then
`saldo = saldo_base - debe + haber`. The `saldo` field is `editable=False` (FR-006). A backdated
entry is computed against the *latest* movement and can leave later-dated rows stale; this is the
documented trigger for `MovimientoLibro.recalcular_saldos(cuenta_id)`, which rebuilds every row from
`saldo_inicial` in `fecha`/`id` order (FR-008).

### 2. FR-007 validation guard (new)

Reject negative `debe`/`haber` and require at least one of them to be non-zero. Enforced at three
layers: DB `CheckConstraint(condition=Q(...))` (Principle 1), `MovimientoLibro.clean()`, and
`MovimientoLibroForm.clean()` for inline form errors.

### 3. Master-detail presentation layer (new)

A single high-contrast template (`conciliacion/libro_bancario.html`) renders:

- **Master**: account selector (list or `<select>` of `CuentaBancaria`, each row showing
  `denominacion`, `banco`, `tipo_cuenta`, `moneda`).
- **Detail**: chronological ledger table (columns `fecha`, `tipo_operacion`, `detalle`, `debe`,
  `haber`, `saldo`) plus the horizontal single-row entry form.

Keyboard-first conventions: natural DOM tab order (`fecha` → `tipo_operacion` → `detalle` → `debe`
→ `haber` → submit), `Enter` submits from any input (native form behavior), `autofocus` on the first
field, `inputmode="decimal"`/`step="0.01"` on amounts, and visible `:focus`/`:focus-visible` outlines
for high contrast.

### 4. Thin views + recalculation endpoint (new)

Views are thin HTTP adapters that delegate to the model engine (no business arithmetic in views).

- `libro_bancario` (GET): render the page for a selected account (defaults to the first account).
- `libro_bancario_crear` (POST): bind `MovimientoLibroForm`; on success redirect to the ledger.
- `libro_bancario_recalcular` (POST): call `MovimientoLibro.recalcular_saldos(cuenta_id)` and redirect.

### 5. Sidebar integration

Add a "Libro Bancario" entry to `templates/base.html` navigation, consistent with existing entries.

## Project Structure

### Documentation (this feature)

```text
specs/002-libro-bancario/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── http-api.md      # Phase 1 (UI/HTTP contract)
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
totalcb/                 # Django project
├── settings.py          # Bootstrap/Alpine static + SQLite absolute path
├── paths.py             # absolute SQLite/static path helper
├── urls.py
└── wsgi.py

conciliacion/            # Django app
├── models.py            # MovimientoLibro (save() engine) + CuentaBancaria
├── forms.py             # MovimientoLibroForm (+ FR-007 clean)
├── views.py             # libro_bancario views (thin adapters)
├── templates/conciliacion/
│   ├── libro_bancario.html       # Master-Detail + horizontal entry form
│   └── _campos_formulario.html
├── static/ (bundled at root)
└── migrations/          # 0005_* FR-007 CheckConstraints

templates/
└── base.html            # add "Libro Bancario" sidebar entry

static/
├── css/bootstrap.min.css
└── js/alpine.min.js

tests/
└── unit/                # test_libro_bancario.py (views/validation) + existing model tests
```

**Structure Decision**: Single Django project + single `conciliacion` app (single-enterprise desktop
scope). The balance engine remains in the model's `save()` as requested; no new service-layer
abstraction is introduced for this feature (unlike the 001 reconciliation engine), keeping the ledger
write path atomic and co-located with the invariant it enforces.

## Complexity Tracking

> Filled because the Constitution Check has one justified violation.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Principle 2 mandates Tailwind CSS; this feature uses offline Bootstrap 5 | Explicit product-owner directive to use offline Bootstrap 5 CSS; the existing shell (`base.html`) and catalog forms already ship Bootstrap 5 (`form-control`, `form-select`, `card`, `table`), so a Bootstrap implementation is consistent with the codebase and avoids a mixed-framework UI | Adopting Tailwind now would require rewriting the existing shell/forms and either re-adding a build step or re-bundling utilities, conflicting with the offline/no-build constraint and duplicating existing Bootstrap markup |

