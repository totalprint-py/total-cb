# Research: Libro Bancario (Bank Ledger)

**Branch**: `002-libro-bancario` | **Date**: 2026-09-10

Phase 0 findings resolving all technical unknowns. Format: Decision / Rationale / Alternatives considered.

## R1. Frontend: offline Bootstrap 5 vs Tailwind (constitution Principle 2)

- **Decision**: Use offline Bootstrap 5 (`static/css/bootstrap.min.css`) with Alpine.js v3 for the
  small amount of reactive behavior (account switching highlight, if needed).
- **Rationale**: The product owner explicitly directed "offline Bootstrap 5 CSS". The existing
  application shell (`templates/base.html`) and every catalog CRUD form already use Bootstrap 5
  utility classes (`form-control`, `form-select`, `card`, `table`, `btn`), and
  `static/css/bootstrap.min.css` is already bundled. Bootstrap 5 gives the high-contrast
  `table-dark`/`bg-dark` components and the responsive grid needed for a Master-Detail layout with no
  build step.
- **Alternatives considered**: (a) Tailwind CSS + Alpine (the constitution's literal wording) — would
  require rewriting the existing shell/forms or mixing two frameworks; rejected as inconsistent with
  the current codebase and the directive. (b) Custom CSS only — more code, no shared component
  vocabulary; rejected for maintainability.

## R2. Running-balance engine placement

- **Decision**: Keep the engine inside `MovimientoLibro.save()` (already implemented); expose the
  repair path via the existing `MovimientoLibro.recalcular_saldos(cuenta_id)` classmethod.
- **Rationale**: The user explicitly requires the engine within the model's `save` method.
  Co-locating the invariant with the write guarantees every insert flows through it;
  `recalcular_saldos` provides the deterministic repair for backdated/corrected entries. SQLite +
  single-user desktop scope make the synchronous per-insert lookup (latest movement) trivially cheap.
- **Alternatives considered**: (a) `pre_save`/`post_save` signals — indirection and harder to reason
  about/roll back; rejected. (b) service-layer-only computation — violates the explicit `save()`
  requirement and would allow `objects.create()`/bulk writes to bypass the invariant.

## R3. Backdated entries and recalculation

- **Decision**: Document backdated inserts as "computed from the latest movement; later-dated rows
  become stale" and provide a visible "Recalcular saldos" action that calls `recalcular_saldos`.
- **Rationale**: Recomputing the whole tail on every insert is unnecessary for the stated single-user
  flow; the spec (Edge Cases) explicitly accepts this behavior if it is detectable and reparable. The
  existing `recalcular_saldos` is idempotent and already unit-tested.
- **Alternatives considered**: (a) recompute the entire ledger on every `save()` — simpler mental
  model but O(n) writes per insert; rejected for unnecessary write amplification. (b) block backdated
  entries — rejected; the spec requires supporting them.

## R4. FR-007 validation strategy (negative amounts / both-zero)

- **Decision**: Enforce at three layers — DB `CheckConstraint(condition=Q(...))` (Principle 1),
  `MovimientoLibro.clean()`, and `MovimientoLibroForm.clean()` for inline errors.
- **Rationale**: The DB constraint is the authoritative guarantee (survives ORM bulk/`update`); model
  `clean()` gives a single validation source callable from forms/admin; form `clean()` surfaces
  Spanish inline messages in the horizontal form.
- **Alternatives considered**: (a) form-only validation — bypassable via admin/ORM; rejected. (b)
  `float` arithmetic — rejected (Principle 5).

## R5. Decimal precision

- **Decision**: Keep `debe`, `haber`, `saldo`, and `saldo_inicial` as
  `DecimalField(max_digits=18, decimal_places=2)` and compute with `decimal.Decimal`.
- **Rationale**: 18,2 is already the implemented schema and satisfies FR-009 (2 dp exact, no `float`).
- **Alternatives considered**: `FloatField` — rejected (Principle 5); `max_digits=19/8` (used by the
  reconciliation engine's import amounts) — not needed here because the ledger convention is cents.

## R6. Keyboard-first Master-Detail (Tab/Enter) + high contrast

- **Decision**: Server-rendered Django template with a natural tab order and native form submission.
  High contrast via Bootstrap `table-dark`/`bg-dark`/`bg-primary` + a strong `:focus-visible` outline.
- **Rationale**: Native HTML `Tab`/`Enter` behavior needs no JS and is the most reliable keyboard
  path. The existing catalog screens already follow a Master-Detail card layout (list + side form);
  the ledger page extends it with a full-width detail area for the table plus a single-row horizontal
  form. Alpine.js is retained only where reactive state is genuinely needed.
- **Alternatives considered**: (a) SPA (React/Vue) — prohibited (heavy frameworks) and would break the
  no-build constraint. (b) heavy JS keyboard handling — unnecessary given native form semantics;
  rejected.
