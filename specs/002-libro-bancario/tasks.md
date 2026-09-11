---
description: "Task list for Libro Bancario (Bank Ledger) — presentation layer, FR-007 validation, end-to-end coverage"
---

# Tasks: Libro Bancario (Bank Ledger)

**Input**: Design documents from `/specs/002-libro-bancario/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: REQUIRED — Constitution Principle 3 (Test-Driven Development, the Test-First imperative) mandates Red-Green-Refactor. Every FR-007 validation, view, and template writes a failing test before its implementation.

**Organization**: Phases are ordered by TDD layer (setup → FR-007 tests → FR-007 impl → view tests → views/URLs → template test → template/UX → verify). Each task carries a `[US#]` label for traceability to the spec's user stories.

## Path Conventions

- **Project**: `totalcb/` (Django project) + `conciliacion/` (single app)
- **Tests**: `tests/unit/` at repo root (pytest + pytest-django)
- **Templates**: `templates/` (app shell) and `conciliacion/templates/conciliacion/` (module templates)
- **Static**: `static/` at repo root (offline Bootstrap 5 + Alpine.js v3)

## Phase 1: Setup (already satisfied)

**Purpose**: Confirm the reused infrastructure from feature 001; no new bootstrap is required.

- [x] T001 [P] Confirm `totalcb/settings.py` already registers `conciliacion`, `TEMPLATES['DIRS']=[BASE_DIR/'templates']`, `STATIC_URL='/static/'`, `STATICFILES_DIRS=[paths.static_root()]`, and SQLite `NAME=paths.database_path()` (absolute path — Principle 4). No change expected.
- [x] T002 [P] Confirm `conciliacion/models.py` already defines `MovimientoLibro` (`save()` running-balance engine + `recalcular_saldos`) and `CuentaBancaria.saldo_inicial`, and that `MovimientoLibroForm` exists in `conciliacion/forms.py`. No change expected.

**Checkpoint**: Reused model/engine/form and desktop-ready settings verified; nothing new blocks the feature.

## Phase 2: Tests First — FR-007 validation (RED)

**Purpose**: Write failing tests for FR-007 before the validation exists in model, DB, or form.

- [x] T003 [P] [US2] Write failing `tests/unit/test_movimiento_libro_validation.py`: `MovimientoLibro.full_clean()` raises `ValidationError` for negative `debe`, negative `haber`, and both-zero `debe`/`haber` (FR-007).
- [x] T004 [P] [US2] Write failing `tests/unit/test_movimiento_libro_constraints.py`: `MovimientoLibro.objects.create()` with negative/both-zero amounts inside `transaction.atomic()` raises `IntegrityError` from the `CheckConstraint(condition=Q(...))` (FR-007, Principle 1).
- [x] T005 [P] [US2] Write failing `tests/unit/test_libro_bancario_forms.py`: `MovimientoLibroForm.clean()` rejects negative `debe`/`haber` and both-zero with Spanish inline errors (FR-007).

**Checkpoint**: All three FR-007 test files FAIL (Red) — constraints/validation do not exist yet.

## Phase 3: Implement FR-007 validation (GREEN)

**Purpose**: Add the DB `CheckConstraint`, model `clean()`, and form `clean()` to satisfy Phase 2.

- [x] T006 [US2] Add to `MovimientoLibro.Meta.constraints` in `conciliacion/models.py`: `CheckConstraint(condition=Q(debe__gte=0))`, `CheckConstraint(condition=Q(haber__gte=0))`, and `CheckConstraint(condition=Q(debe__gt=0) | Q(haber__gt=0))` (Principle 1; no legacy `check=`).
- [x] T007 [US2] Generate `conciliacion/migrations/0005_*` via `python manage.py makemigrations conciliacion` (applies the FR-007 CheckConstraints).
- [x] T008 [US2] Implement `MovimientoLibro.clean()` in `conciliacion/models.py` mirroring FR-007 (negative debe/haber, at-least-one-nonzero) so `full_clean()`/admin surface the errors.
- [x] T009 [US2] Implement `MovimientoLibroForm.clean()` in `conciliacion/forms.py` adding the FR-007 checks with Spanish `ValidationError` messages.

**Checkpoint**: `pytest tests/unit/test_movimiento_libro_validation.py tests/unit/test_movimiento_libro_constraints.py tests/unit/test_libro_bancario_forms.py` passes (Green). T006→T008 share `conciliacion/models.py` (sequential).

## Phase 4: Tests First — Views & URLs (RED)

**Purpose**: Write failing view tests before any view or URL code exists.

- [x] T010 [US1] Write failing `tests/unit/test_libro_bancario_views.py` (GET `libro_bancario`): 200 + context `cuentas`, selected `cuenta`, `movimientos` ordered by `fecha`/`id`, `form`, and `saldo_inicial`; empty-ledger state when the account has no movements (FR-001/002/003).
- [x] T011 [US2] In the same file, POST `libro_bancario_crear`: persists the movement with `saldo = saldo_base - debe + haber`, redirects to `libro_bancario?cuenta=<id>`; invalid form re-renders 200 with bound errors; non-POST returns 405 (FR-005/006/007).
- [x] T012 [US3] In the same file, POST `libro_bancario_recalcular`: rebuilds every `saldo` from `saldo_inicial` in `fecha`/`id` order and redirects; missing/invalid `cuenta` returns 404; non-POST returns 405 (FR-008).

**Checkpoint**: View tests FAIL (Red) — URL patterns and views do not exist yet. T010→T012 share one file (sequential).

## Phase 5: Implement Views & URLs (GREEN)

**Purpose**: Add the thin HTTP adapters that delegate to the model engine (no business arithmetic in views).

- [x] T013 [US1] Add URL patterns `libro_bancario`, `libro_bancario_crear`, `libro_bancario_recalcular` to `conciliacion/urls.py` (un-namespaced, matching existing convention).
- [x] T014 [US1] Implement the `libro_bancario` GET view in `conciliacion/views.py`: select account via query param `cuenta` (fallback to first account), build context `cuentas`/`cuenta`/`movimientos`/`form`/`saldo_inicial` per the HTTP contract; when no `CuentaBancaria` rows exist, return the empty state (`cuentas` empty, `cuenta=None`, `movimientos` empty, `form` still present) instead of crashing.
- [x] T015 [US2] Implement the `libro_bancario_crear` POST view in `conciliacion/views.py`: resolve `cuenta` out-of-band (URL/hidden field) and assign `form.instance.cuenta`; on valid form, save (delegating to the model engine) and redirect 302 to `libro_bancario?cuenta=<id>`; on invalid form, re-render with the full GET context repopulated (`cuentas`, selected `cuenta`, `movimientos`, bound `form`, and `saldo_inicial`) showing Spanish inline errors; non-POST → 405.
- [x] T016 [US3] Implement the `libro_bancario_recalcular` POST view in `conciliacion/views.py`: `get_object_or_404(CuentaBancaria, ...)`, call `MovimientoLibro.recalcular_saldos(cuenta_id)`, redirect; non-POST → 405.

**Checkpoint**: `pytest tests/unit/test_libro_bancario_views.py` passes (Green). T014→T016 share `conciliacion/views.py` (sequential).

## Phase 6: Test First — Template & UX (RED → GREEN)

**Purpose**: Prove the Master-Detail template contract, then implement it.

- [x] T017 [US1] [US2] [US3] Write failing `tests/unit/test_libro_bancario_templates.py`: render `libro_bancario`; assert Spanish labels, ledger columns (`fecha`, `tipo_operacion`, `detalle`, `debe`, `haber`, `saldo`), horizontal form field order (`fecha` → `tipo_operacion` → `detalle` → `debe` → `haber`), account `Banco`/`TipoCuenta`/`Moneda` display, no editable `saldo` input, and the "Recalcular saldos" action (FR-001/003/004/006).
- [x] T018 [US1] [US2] [US3] Implement `conciliacion/templates/conciliacion/libro_bancario.html`: high-contrast Master-Detail (`table-dark`/`bg-dark`), chronological ledger with running `saldo` column, single-row horizontal entry form (`autofocus`, `inputmode="decimal"`, visible `:focus-visible`), and the recalculation button.
- [x] T019 [P] Add the "Libro Bancario" sidebar entry to `templates/base.html` navigation (Spanish label, consistent with existing entries).

**Checkpoint**: `pytest tests/unit/test_libro_bancario_templates.py` passes (Green); the page renders end-to-end.

## Phase 7: Verification & Polish

- [x] T020 Run the full suite `python -m pytest -q` (all green; no regressions in the existing `test_movimiento_libro.py`).
- [x] T021 [P] Execute `quickstart.md` manual scenarios 1–7 (view ledger, horizontal entry + running balance, FR-007 inline errors, recalculation idempotence).
- [x] T022 [P] Run `python manage.py makemigrations --check` and `python manage.py collectstatic --noinput` (migration state + desktop-readiness static collection, Principle 4).

**Checkpoint**: Feature complete; SC-001…SC-005 verifiable.

## Dependencies & Execution Order

- Phase 1 → Phase 2 → Phase 3 (FR-007) and Phase 4 → Phase 5 (views). Phase 4/5 also depend on Phase 3 (views use the validated model/form). Phase 6 depends on Phase 5; Phase 7 depends on all.
- Tests MUST be written and confirmed FAILING before implementation (Principle 3 Red-Green-Refactor).
- Same-file tasks are sequential — not `[P]`: `conciliacion/models.py` (T006→T008), `conciliacion/views.py` (T014→T016), view-test file (T010→T012).

### Story → Task Traceability

| Story | Tasks |
|---|---|
| US1 (select account + view ledger) | T010, T013, T014, T017, T018 |
| US2 (horizontal entry + running balance + FR-007) | T003, T004, T005, T006, T007, T008, T009, T011, T015, T017, T018 |
| US3 (recalculation) | T012, T016, T017, T018 |

## Notes

- Money is `decimal.Decimal` (`DecimalField(max_digits=18, decimal_places=2)`); `float` is forbidden (FR-009, Principle 5).
- All domain constraints use `CheckConstraint(condition=Q(...))`; the legacy `check=` is forbidden (Principle 1).
- FR-009 (Decimal) and FR-010 (PROTECT/CASCADE) are already satisfied by the existing model — verified, not re-implemented.
- Offline Bootstrap 5 + Alpine.js v3 per the plan's documented Principle 2 deviation; no client-side build step (Principle 4).


## Convergence

**Status**: Converged.

- T021 (manual UI scenarios 1-7) verified by the Product Owner: account selection + ledger view, horizontal entry + running balance, FR-007 inline errors, and recalculation idempotence.
- All tasks T001-T022 complete; full test suite green; `makemigrations --check` clean; static files collected.
- Interface paths and DB constraint names reconciled with `contracts/http-api.md` and `data-model.md`.

