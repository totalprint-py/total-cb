# Tasks: Conciliación Bancaria (Extracto y Punteo)

**Input**: Design documents from `/specs/004-conciliacion-bancaria/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: **REQUIRED** — this feature is TDD-first (Constitution Principle 3 is non-negotiable: Red-Green-Refactor).
Every story writes its failing tests BEFORE implementation.

**Organization**: Tasks are grouped by user story (US1→US4) so each story is independently testable. P1 stories precede
P2. Note: US4 (lock) is P1 but mechanically depends on US2 (`despuntear`); it is sequenced after US2 for that reason.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Exact file paths included in every description

## Path Conventions

- **Django app**: `conciliacion/` and `conciliacion/templates/conciliacion/`
- **Tests**: `tests/unit/`
- **Shared sidebar**: `templates/base.html`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing single-app Django project baseline before the new feature layer.

- [x] T001 Confirm baseline: verify `git branch --show-current` is `004-conciliacion-bancaria`, the latest migration is
  `conciliacion/migrations/0007_*.py` (the anchor for the new `0008`), and confirm the green baseline
  `python -m pytest tests/unit -q` → **337 passed**. All new work is RED-first (write failing tests before implementation).

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The data-model layer every user story depends on. Must be green before any story work begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundational (write FIRST — must FAIL)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T002 [P] Write failing model tests in `tests/unit/test_extracto_modelos.py` asserting `MovimientoExtracto` fields
  (`cuenta_bancaria` FK PROTECT, `fecha`, `referencia` blank, `detalle`, `importe` via `ImporteDecimalField`, `origen`
  choices default `manual`, `conciliado` default False), the non-zero `importe` and `origen` `CheckConstraint(condition=Q(...))`,
  Meta `ordering=["fecha","id"]`, `Punteo` `UniqueConstraint` on each FK (strict 1:1), and `AuditoriaPunteo` fields
  (`fecha_hora` auto, `accion` in `puntear|despuntear`, FKs to both sides PROTECT, `usuario`) with its `accion`
  `CheckConstraint(condition=Q(...))`.

### Implementation for Foundational

- [x] T003 Add `MovimientoExtracto`, `Punteo`, and `AuditoriaPunteo` models to `conciliacion/models.py` (reuse
  `ImporteDecimalField` and `CheckConstraint(condition=Q(...))`; `UniqueConstraint` on both `Punteo` FKs; sign invariant
  `importe == libro.debe - libro.haber`; `AuditoriaPunteo` `accion` `CheckConstraint(condition=Q(...))`).
- [x] T004 Generate migration via `python manage.py makemigrations conciliacion` → `conciliacion/migrations/0008_movimientoextracto_punteo_auditoria.py`;
  confirm the migration uses `CheckConstraint(condition=Q(...))` only (no legacy `check=`), then run
  `python -m pytest tests/unit/test_extracto_modelos.py` to green.

**Checkpoint**: Data model foundation ready — user story implementation can begin.

## Phase 3: User Story 1 - Ingest the bank statement (extracto) (Priority: P1) 🎯 MVP

**Goal**: Load `.xlsx`/`.csv` statements into `MovimientoExtracto` bound to a `CuentaBancaria`, via bulk import and manual CRUD.

**Independent Test**: Upload/create `MovimientoExtracto` rows against a known `CuentaBancaria`; assert persisted rows and
fields with no matching involved.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T005 [P] [US1] Write failing import parser tests in `tests/unit/test_extracto_importadores.py` covering: canonical
  `fecha,referencia,detalle,importe` header; Spanish aliases (`fecha`/`date`, `detalle`/`descripcion`/`concepto`,
  `importe`/`monto`, `referencia`/`ref`/`numero`); the `debe`+`haber` two-column layout normalized to `importe = DEBE - HABER`
  (case-insensitive headers, ignore `OPERACIÓN`/`SALDO`); and the benchmark fixture row skip of `Saldo Anterior` + footer
  totals (fixture `1 Continental Guaranies.xlsx` sheet `CONTINENTAL`).
- [x] T006 [P] [US1] Write failing import error + CRUD view tests in `tests/unit/test_extracto_vistas.py` covering
  missing-header/empty-file/zero/`float`/bad-date rejection (all-or-nothing rollback with Spanish per-row errors) and
  manual `extracto_list`/`extracto_create`/`extracto_update`/`extracto_delete` flows.

### Implementation for User Story 1

- [x] T007 [US1] Implement the parser in `conciliacion/importadores.py` (openpyxl for `.xlsx`, stdlib `csv` for `.csv`;
  normalize `importe = DEBE - HABER`; case-insensitive header matching; skip preamble/footer rows) per
  `contracts/import-format.md`.
- [x] T008 [US1] Implement `importar_extracto(cuenta, archivo, formato)` (parse + `transaction.atomic` bulk-create,
  all-or-nothing) in `conciliacion/punteo.py`, plus `ExtractoImportarForm` (cuenta + archivo) in `conciliacion/forms.py`.
- [x] T009 [US1] Implement `MovimientoExtracto` CRUD + import views and URLs (`extracto_list`, `extracto_create`,
  `extracto_update`, `extracto_delete`, `extracto_importar`) in `conciliacion/views.py` and `conciliacion/urls.py`.
- [x] T010 [US1] Create templates `conciliacion/templates/conciliacion/extracto_list.html`, `extracto_form.html`, and
  `extracto_importar.html` with Spanish labels. Then run `python -m pytest tests/unit/test_extracto_importadores.py tests/unit/test_extracto_vistas.py` to green.

## Phase 4: User Story 2 - Punteo: match extracto against libro (Priority: P1)

**Goal**: Dual-list screen links an unmatched `MovimientoExtracto` to a same-account unmatched `MovimientoLibro`, marking both `conciliado`.

**Independent Test**: Seed unmatched rows, select a matching pair, assert both flip to `conciliado` and the `Punteo` link persists.

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US2] Write failing punteo service tests in `tests/unit/test_extracto_servicios.py` covering `puntear`
  (same account + EXACT `decimal.Decimal` equality after `quantize_to_moneda` → link + both `conciliado`), `despuntear`
  (removes link + resets both flags + writes an atomic `AuditoriaPunteo` row), mismatch `ImporteNoCoincideError`,
  cross-account rejection, and 1:1 `UniqueConstraint`.
- [x] T012 [P] [US2] Write failing punteo view + template tests in `tests/unit/test_extracto_vistas.py` (POST `puntear`
  302 on success / 400 on mismatch; POST `despuntear`) and `tests/unit/test_punteo_templates.py` (dual-list excludes
  already-`conciliado` records; empty states).

### Implementation for User Story 2

- [x] T013 [US2] Implement typed errors (`ImporteNoCoincideError`, `ConciliadoBloqueadoError`, `EstadoInvalidoError`) and
  `puntear(*, extracto, libro)` / `despuntear(*, extracto)` in `conciliacion/punteo.py` (atomic; exact-to-the-cent
  equality; each transition writes an `AuditoriaPunteo` row in the same transaction).
- [x] T014 [US2] Implement `punteo` (GET dual-list), `puntear` (POST), `despuntear` (POST) views + URLs in
  `conciliacion/views.py` and `conciliacion/urls.py`.
- [x] T015 [US2] Create `conciliacion/templates/conciliacion/punteo.html` (Alpine.js dual-list mirroring `matcher.html`,
  offline Bootstrap 5) and add lock indicators to `extracto_list.html`. Run
  `python -m pytest tests/unit/test_extracto_servicios.py tests/unit/test_extracto_vistas.py tests/unit/test_punteo_templates.py` to green.

## Phase 5: User Story 4 - Lock matched (conciliado) records (Priority: P1)

**Goal**: A `conciliado` `MovimientoLibro` (and symmetrically its `MovimientoExtracto`) is locked against edit/delete via
every surface; only `despuntear` releases it (audited). Depends on US2 for `despuntear`.

**Independent Test**: Mark a `MovimientoLibro` `conciliado`; assert model `delete`, update view, and delete view all raise
typed errors, and only `despuntear` releases it.

### Tests for User Story 4 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T016 [P] [US4] Extend `tests/unit/test_movimiento_libro.py` with `ConciliadoBloqueadoError` cases (model `delete()`
  guard, plus existing update/delete views) asserting a Spanish error and unchanged data for `conciliado` rows.
- [x] T017 [P] [US4] Write failing symmetric-lock tests in `tests/unit/test_extracto_vistas.py` (`extracto_update` /
  `extracto_delete` return 400 while `conciliado`; `despuntear` is the only release).

### Implementation for User Story 4

- [x] T018 [US4] Harden `MovimientoLibro.delete()` and add `MovimientoExtracto.delete()` guards (raise
  `ConciliadoBloqueadoError` while `conciliado`) in `conciliacion/models.py`.
- [x] T019 [US4] Add lock re-validation to `extracto_update`/`extracto_delete` and the libro update/delete views in
  `conciliacion/views.py`; hide/disable Edit/Delete buttons on `conciliado` rows in
  `conciliacion/templates/conciliacion/libro_bancario.html` and `extracto_list.html`. Run
  `python -m pytest tests/unit/test_movimiento_libro.py tests/unit/test_extracto_vistas.py` to green.

## Phase 6: User Story 3 - Create a book entry from a statement row (Priority: P2)

**Goal**: From a statement-only `MovimientoExtracto`, create the counterpart `MovimientoLibro`, map the sign to `debe`/`haber`,
recompute running `saldo`, and auto-link+mark both `conciliado` in one transaction.

**Independent Test**: Invoke on a single unmatched `MovimientoExtracto`; assert the created `MovimientoLibro` (sign mapping,
recomputed `saldo`) is immediately linked via `Punteo` with no punteo selection step.

### Tests for User Story 3 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T020 [P] [US3] Write failing `crear_asiento_desde_extracto` tests in `tests/unit/test_extracto_servicios.py`
  (correct `debe`/`haber` sign mapping, `saldo = saldo_base + debe - haber` recomputed chronologically via
  `MovimientoLibro.recalcular_saldos`, both records linked + `conciliado`, atomic; rejects an already-`conciliado` source)
  and that the created `tipo_operacion` resolves via `TipoOperacion.objects.get_or_create(codigo="AJUSTE-BANCARIO")`.

### Implementation for User Story 3

- [x] T021 [US3] Implement `crear_asiento_desde_extracto(*, extracto)` in `conciliacion/punteo.py` (resolve
  `tipo_operacion` via `TipoOperacion.objects.get_or_create(codigo="AJUSTE-BANCARIO", defaults={"nombre": "Ajuste
  Bancario"})` → sign-map to `debe`/`haber` → create `MovimientoLibro` → recompute `saldo` → link + mark `conciliado`,
  single transaction).
- [x] T022 [US3] Implement `crear_asiento_extracto` view + URL + pre-filled form in `conciliacion/views.py`,
  `conciliacion/urls.py`, `conciliacion/forms.py`.
- [x] T023 [US3] Create `conciliacion/templates/conciliacion/crear_asiento_form.html`. Run
  `python -m pytest tests/unit/test_extracto_servicios.py` to green.

**Checkpoint**: US3 — statement-only items can be converted to reconciled book entries.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Integration glue and final validation across all stories.

- [x] T024 [P] Add "Extracto Bancario" and "Punteo" sidebar entries to `templates/base.html` (consistent with existing nav).
- [x] T025 Run the full `quickstart.md` validation and `python -m pytest -q`; all suites green (the **337 passed**
  baseline plus the new Feature 004 tests).
- [x] T026 [P] Verify constitution compliance: Principle 0 (Spanish identifiers/UI, English docs), Principle 1
  (`CheckConstraint(condition=Q(...))` only), Principle 3 (every story has failing-then-green test evidence), Principle 5
  (`Decimal` only, exact-to-cent equality).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirm baseline first.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phases 3-6)**: All depend on Foundational completion; proceed in priority order P1 → P2.
- **Polish (Phase 7)**: Depends on all desired stories.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no other story dependency.
- **US2 (P1)**: Can start after Foundational — uses `MovimientoExtracto`/`MovimientoLibro` from the model layer.
- **US4 (P1)**: Depends on US2 (needs `despuntear` and the `conciliado` state); sequenced after US2.
- **US3 (P2)**: Depends on Foundational + US2's `puntear`/`despuntear` (re-uses the linking path for auto-link).

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Red-Green-Refactor).
- Models before services; services before endpoints; core before integration.
- Story complete before moving to the next priority.

### Parallel Opportunities

- All test tasks for a story marked `[P]` can run in parallel (different files).
- US1 import parser tests (T005) and view tests (T006) are independent files.
- US2 service tests (T011) and view/template tests (T012) are independent files.

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational) → data model green.
2. Complete Phase 3 (US1) → STOP and VALIDATE import + CRUD independently.
3. Complete Phase 4 (US2) → STOP and VALIDATE punteo matching independently.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. Add US1 → validate → (MVP: statement ingestion).
3. Add US2 → validate → (MVP: statement matching).
4. Add US4 → validate → (integrity: immutable reconciled records).
5. Add US3 → validate → (full loop: create-book-entry for statement-only items).

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to its user story for traceability.
- Verify tests fail before implementing; commit after each task or logical group.
- Avoid same-file conflicts and cross-story dependencies that break independence.

