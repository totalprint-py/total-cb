---
description: "Task list for Phase 1 - Core Reconciliation Engine"
---

# Tasks: Core Reconciliation Engine (Phase 1)

**Input**: Design documents from `/specs/001-core-reconciliation-engine/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/service-layer.md, quickstart.md

**Tests**: REQUIRED — Constitution Principle 3 mandates TDD (Red-Green-Refactor). Every layer writes a failing test before its implementation.

**Organization**: Phases are ordered by SDD/TDD layer (setup → tests → models → services → UX → verify) per the Constitution, not by user story. Each task carries a `[US#]` label for traceability to the spec's user stories.

## Path Conventions

- **Project**: `totalcb/` (Django project) + `conciliacion/` (single app)
- **Tests**: `tests/unit/`, `tests/integration/`, `tests/contract/` at repo root
- **Templates/static**: `templates/` and `static/` at repo root; app templates under `conciliacion/templates/conciliacion/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Bootstrap the Django project, absolute pathing wrappers (`sys._MEIPASS` / `%LOCALAPPDATA%`), and base configuration.

- [x] T001 [P] Create `requirements.txt` at repo root pinning `Django>=5.1,<6.0`, `pytest`, `pytest-django`.
- [x] T002 [P] Create `pytest.ini` at repo root with `DJANGO_SETTINGS_MODULE=totalcb.settings`, `python_files = test_*.py tests.py`, `testpaths = tests`.
- [x] T003 Bootstrap the Django project by running `django-admin startproject totalcb .`, producing `manage.py`, `totalcb/settings.py`, `totalcb/urls.py`, `totalcb/wsgi.py`, `totalcb/asgi.py`.
- [x] T004 Create the app by running `python manage.py startapp conciliacion`, producing `conciliacion/models.py`, `conciliacion/views.py`, `conciliacion/apps.py`, `conciliacion/migrations/`.
- [x] T005 Implement `totalcb/paths.py` with `app_root()`, `data_dir()`, `database_path()`, `static_root()` resolving `sys._MEIPASS` (frozen) vs `BASE_DIR` (dev) for read-only assets and `%LOCALAPPDATA%\total-cb\` for the writable SQLite DB (Principle 4, FR-011).
- [x] T006 Configure `totalcb/settings.py`: `DATABASES['default']` = SQLite with absolute `NAME=paths.database_path()`; add `conciliacion` to `INSTALLED_APPS`; `TEMPLATES['DIRS']=[BASE_DIR/'templates']`; `STATIC_URL='/static/'` and `STATICFILES_DIRS=[paths.static_root()]`.

**Checkpoint**: Django project boots and every runtime path resolves absolutely (no bare relative paths).

---

## Phase 2: Tests First — Catalogs, Models, CheckConstraints (RED)

**Purpose**: Write failing tests (TDD Red) for the data model before any model code exists. Cover catalog/operational fields, `DecimalField` enforcement, and `CheckConstraint(condition=Q(...))` database constraints.

- [x] T007 [P] Create `tests/__init__.py`, `tests/unit/__init__.py`, and `tests/conftest.py` with pytest-django fixtures (catalog/movement factory helpers, `db` access).
- [x] T008 [P] [US2] Write failing `tests/unit/test_models_catalogos.py`: `Banco`, `TipoCuenta`, `Moneda`, `TipoOperacion`, `ConceptoAjuste` fields; `codigo` unique/required; `Moneda.cantidad_decimales` required non-negative; monetary fields are `DecimalField` (never `FloatField`).
- [x] T009 [P] [US1] [US4] Write failing `tests/unit/test_models_operativos.py`: `LoteImportacion` unique import identity (FR-012 dedupe), `CuentaBancaria`, `MovimientoBancario`/`MovimientoInterno` (`DecimalField` `importe`, `en_consulta` default `False`, optional `notas`, FK to `LoteImportacion`/`Moneda`), `Conciliacion` states, detail unique-pairs, `AjusteConciliacion`; currency-match validation (movement `moneda` == account `moneda`).
- [x] T010 [P] [US2] Write failing `tests/unit/test_motor_conciliacion.py`: `Conciliacion` (`estado` válido draft/committed/reverted vía `CheckConstraint(condition=Q(...))` con `name` explícito), `DetalleConciliacionBancaria`/`DetalleConciliacionInterna` (par único `(conciliacion, movimiento)` vía `UniqueConstraint`), y `AjusteConciliacion` (`importe` `DecimalField` nunca `FloatField`; asignar `float` lanza error de tipo/validación forzando `decimal.Decimal`).

**Checkpoint**: All Phase 2 tests fail for the right reason (missing models/constraints).

---

## Phase 3: Implement Database Models (GREEN)

**Purpose**: Implement `conciliacion/models.py` with exact `DecimalField` money columns and `CheckConstraint(condition=Q(...))` — never `check=` (Principle 1, FR-007/FR-009).

- [x] T011 [US2] Implement catalog models in `conciliacion/models.py`: `Banco`, `TipoCuenta`, `Moneda` (`cantidad_decimales = PositiveIntegerField` + `CheckConstraint(condition=Q(cantidad_decimales__gte=0), name='moneda_cantidad_decimales_no_negativa')`), `TipoOperacion`, `ConceptoAjuste` (unique `codigo`, `nombre`).
- [x] T012 [US1] [US4] Implement operational models in `conciliacion/models.py`: `LoteImportacion` (unique import identity for FR-012 dedupe), `CuentaBancaria`, `MovimientoBancario`, `MovimientoInterno`, `Conciliacion` (`estado` choices draft/committed/reverted), `DetalleConciliacionBancaria`, `DetalleConciliacionInterna` (unique `(conciliacion, movimiento)` pairs), `AjusteConciliacion`; all money = `DecimalField(max_digits=19, decimal_places=8)`; `clean()` enforces movement↔account currency match.
- [x] T013 Generate and apply migrations (`python manage.py makemigrations conciliacion` + `python manage.py migrate`); re-run Phase 2 tests to GREEN.

## Phase 4: Service-Layer Tests (RED)

**Purpose**: TDD for `conciliacion/services.py` — contract + unit tests for the pure functions (Zero-Sum validation, decimal guard, adjustment creation, matching, rollback on error).

- [x] T014 [P] [US1] Write failing `tests/contract/test_service_layer_contract.py`: assert each contract in `contracts/service-layer.md` — `assert_decimal` (`float` → `TypeError`), `commit_reconciliation` atomic rollback on `ZeroSumError`, `create_ajuste`, `match_movimientos` (`AmountMismatchError`), `revert_conciliacion` (`EstadoInvalidoError`), `flag_en_consulta`, `set_nota`.
- [x] T015 [P] [US1] Write failing `tests/unit/test_services_decimal.py`: `assert_decimal` rejects `float`; `quantize_to_moneda` rounds to `Moneda.cantidad_decimales` via `Decimal.quantize(..., ROUND_HALF_EVEN)`; zero-amount handled without breaking Zero-Sum.
- [x] T016 [P] [US1] Write failing `tests/unit/test_services_commit.py`: balanced totals commit; one-cent imbalance raises `ZeroSumError` and rolls back EVERYTHING (no `Conciliacion`, no details); empty reconciliation commits trivially.
- [x] T017 [P] [US3] Write failing `tests/unit/test_services_ajuste.py`: `create_ajuste` persists a `Decimal` adjustment feeding the Zero-Sum equation; rejects `float` and non-draft `Conciliacion`.
- [x] T018 [P] [US8] Write failing `tests/unit/test_services_match.py`: exact-cent amounts match; one-cent difference raises `AmountMismatchError`; extreme date gap emits non-blocking `DateGapWarning`.
- [x] T019 [P] [US5] [US6] [US7] Write failing `tests/unit/test_services_flags_revert.py`: `flag_en_consulta` toggles without removing from the pending list; `set_nota` persists without touching amount/date/state; `revert_conciliacion` unlocks committed records and raises `EstadoInvalidoError` for draft/already-reverted.

**Checkpoint**: All Phase 4 tests fail for the right reason (missing `services.py`).

---

## Phase 5: Implement `services.py` (GREEN)

**Purpose**: Implement the pure domain layer with `@transaction.atomic` orchestrators and strict Zero-Sum enforcement (FR-006, FR-008, FR-010, FR-013–FR-015, Principle 5).

- [x] T020 Implement typed exceptions (`ZeroSumError`, `AmountMismatchError`, `EstadoInvalidoError`, `DateGapWarning`) and helpers `assert_decimal` + `quantize_to_moneda` in `conciliacion/services.py`.
- [x] T021 Implement pure functions `flag_en_consulta`, `set_nota`, `match_movimientos` (exact-amount match, non-blocking date-gap warning), `create_ajuste` in `conciliacion/services.py`.
- [x] T022 Implement `@transaction.atomic` orchestrators `commit_reconciliation` (compute `Sum(Bancario) - Sum(Interno) + Sum(Ajustes)`, raise `ZeroSumError` on non-zero → full rollback) and `revert_conciliacion` (unlock records) in `conciliacion/services.py`; re-run Phase 4 tests to GREEN.

## Phase 6: Views, URLs, Forms & Hybrid UX (RED→GREEN)

**Purpose**: Thin HTTP adapters + Tailwind/Alpine split-screen matcher and a printable "Manual Checking Report" with `@media print` (FR-016/FR-017, Principle 2).

- [x] T023 [P] [US2] [US6] [US7] Write failing `tests/integration/test_views_operaciones.py`: catalog CRUD, `en_consulta` flag POST, and `notas` POST return 200/302 and reflect changes; assert views delegate to `services.py` (no business logic in views).
- [x] T024 [P] [US9] Write failing `tests/integration/test_views_ux.py`: split-screen matcher renders bank+internal side-by-side; "Manual Checking Report" includes `print:hidden`/`no-print` + `@media print`; date-gap warning banner present but non-blocking.
- [x] T025 [US2] Implement `conciliacion/forms.py` ModelForms for catalogs, `notas`, and `en_consulta`.
- [x] T026 [P] [US9] Implement `templates/base.html` (sidebar + main, Tailwind utilities) and `conciliacion/templates/conciliacion/matcher.html` (split-screen `lg:grid-cols-2`, Alpine.js v3 `x-data`/`x-for`/`@click`, "En Consulta" toggle, date-gap banner) + `conciliacion/templates/conciliacion/reporte_manual.html` (print-only "Manual Checking Report") + catalog list/form templates.
- [x] T027 [P] [US9] Implement static assets: pre-built Tailwind `static/css/tailwind.css`, Alpine.js v3 `static/js/alpine.min.js`, and `static/css/print.css` with `@media print { .no-print { display: none !important; } }`.
- [ ] T028 [US2] [US6] [US7] Implement thin views in `conciliacion/views.py` for catalog CRUD, `flag_en_consulta`, and `set_nota` (parse/validate HTTP, delegate to `services.py`).
- [ ] T029 [US9] Implement split-screen matcher + "Manual Checking Report" views in `conciliacion/views.py`.
- [ ] T030 Implement `conciliacion/urls.py` and wire `totalcb/urls.py` (`path('', include('conciliacion.urls'))`); re-run Phase 6 tests to GREEN.

---

## Phase 7: Verification

**Purpose**: Prove the feature end-to-end against quickstart scenarios and Django system checks.

- [ ] T031 Run `python manage.py check` — no system errors, no deprecated `check=` usage, migrations consistent.
- [ ] T032 Run the full suite `pytest` (unit + integration + contract) — all green.
- [ ] T033 Execute `quickstart.md` validation scenarios 1–8: Zero-Sum commit/rollback, Decimal enforcement, date tolerance, "En Consulta", notas, duplicate import (FR-012), revert unlock.
- [ ] T034 [P] Run `python manage.py collectstatic --noinput` and verify `totalcb/paths.py` resolves absolute static/SQLite paths in dev (Principle 4 desktop readiness).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately.
- **Phase 2 (Tests)**: Depends on Phase 1 (Django settings/pytest configured). Tests import not-yet-existing models → must FAIL first.
- **Phase 3 (Models)**: Depends on Phase 2 (TDD Red) — implement to make Phase 2 tests pass.
- **Phase 4 (Service tests)**: Depends on Phase 3 (models must exist for service tests to import/assert against).
- **Phase 5 (Services)**: Depends on Phase 4 — implement to make Phase 4 tests pass.
- **Phase 6 (Views/UX)**: Depends on Phase 5 (views delegate to services).
- **Phase 7 (Verification)**: Depends on Phase 6.

### Within Each Layer

- Tests MUST be written and confirmed FAILING before implementation (Principle 3).
- Models before services; services before views/endpoints; core logic before integration.
- Same-file tasks (`conciliacion/models.py` T011→T012; `conciliacion/services.py` T020→T022; `conciliacion/views.py` T028→T029) are strictly sequential — not `[P]`.

### Parallel Opportunities

- Phase 1: T001, T002 are independent of T003–T006.
- Phase 2: T008, T009, T010 are independent files → all `[P]`.
- Phase 4: T014–T019 are independent files → all `[P]`.
- Phase 6: T023, T024 (tests) and T026, T027 (templates/static) are independent files → `[P]`.

### Story → Task Traceability

| Story | Tasks |
|---|---|
| US1 (reconciliation) | T009, T012, T014, T015, T016 |
| US2 (catalogs) | T008, T010, T011, T023, T025, T028 |
| US3 (adjustments) | T017, T021 |
| US4 (trace to batch) | T009, T012 |
| US5 (revert unlock) | T019, T022 |
| US6 ("En Consulta") | T019, T021, T023, T028 |
| US7 (notas) | T019, T021, T023, T028 |
| US8 (date-tolerant match) | T018, T021 |
| US9 (hybrid UX) | T024, T026, T027, T029 |

---

## Implementation Strategy

### MVP First (Reconciliation Core)

1. Complete Phase 1 → 2 → 3 → 4 → 5.
2. **STOP and VALIDATE**: the Zero-Sum commit/rollback, Decimal enforcement, matching, and adjustment flows are fully tested and green (US1/US3/US5/US8 core).
3. Add Phase 6 for the hybrid UX (US2/US6/US7/US9).
4. Finish with Phase 7 verification.

### Incremental Delivery

- Setup + models + services = the engine's correctness-critical core, independently testable.
- Views/UX add operator-facing value without changing domain logic.
- Each phase commits after its tests turn green.

---

## Notes

- `[P]` tasks = different files, no dependencies.
- `[Story]` labels map each task to a spec user story for traceability (phases are layer-ordered, not story-ordered).
- Verify tests fail before implementing (Red-Green-Refactor).
- Money is `decimal.Decimal` everywhere; `float` raises `TypeError` at the service boundary (FR-007).
- Zero-Sum must hold atomically at commit; any non-zero result rolls back the entire transaction (FR-006, SC-001).
- All domain constraints use `CheckConstraint(condition=Q(...))`; `check=` is forbidden (Principle 1).
- No runtime client-side build step: Tailwind is pre-compiled, Alpine.js served as a static file (Principle 2).
- Every runtime path resolves absolutely via `totalcb/paths.py` (Principle 4).

