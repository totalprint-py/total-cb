# Phase 0 Research: Core Reconciliation Engine

**Branch**: `001-core-reconciliation-engine` | **Date**: 2026-09-04

Research resolving the Technical Context unknowns and confirming technology choices. Each entry
records Decision, Rationale, and Alternatives considered.

## R1 — Django project structure & desktop packaging

- **Decision**: Single Django project (`totalcb`) with one app (`conciliacion`), packaged as a
  single Windows `.exe` with PyInstaller.
- **Rationale**: Single-enterprise internal desktop tool; one app keeps models, services, views,
  and templates cohesive and simple to freeze.
- **Alternatives considered**: Multiple Django apps (rejected — unnecessary for ~14 related
  entities); FastAPI/Flask (rejected — constitution mandates Django 5.1+).

## R2 — Decimal storage strategy (per-currency precision)

- **Decision**: Store every monetary value in a `DecimalField` with a generous fixed physical
  precision (`max_digits=19, decimal_places=8`) and enforce the *currency-specific* precision at
  the service/validation layer using `Decimal.quantize()` with an explicit rounding mode.
- **Rationale**: A single physical column supports all currencies; the per-currency
  `cantidad_decimales` rule is a domain invariant enforced deterministically (never `float`).
  SQLite cannot vary `decimal_places` per row.
- **Alternatives considered**: One column per precision (rejected — schema explosion); storing
  TEXT/INTEGER minor units (rejected — loses Decimal arithmetic ergonomics).

## R3 — CheckConstraint syntax

- **Decision**: All domain constraints in `Meta.constraints` using
  `models.CheckConstraint(condition=Q(...))`.
- **Rationale**: Constitution Principle 1 mandates this; `check=` is deprecated in Django 5.1+.
- **Alternatives considered**: `check=` argument (rejected — forbidden); raw-SQL migrations
  (rejected — less portable/auditable).

## R4 — Transactional Zero-Sum

- **Decision**: Wrap the reconcile+validate+persist sequence in a single
  `@transaction.atomic`-decorated service function; raise `ZeroSumError` to force full rollback.
- **Rationale**: Atomicity guarantees no partial `Conciliacion`/details persist when the
  equation fails (FR-006, SC-001).
- **Alternatives considered**: Manual savepoint juggling (rejected — error-prone); validating in
  the view (rejected — violates service-layer abstraction).

## R5 — sys._MEIPASS path resolution

- **Decision**: A single path helper returns `sys._MEIPASS` (frozen) or `BASE_DIR` (dev) for
  read-only bundled assets, and a separate per-user writable directory
  (`%LOCALAPPDATA%\total-cb\`) for the SQLite DB.
- **Rationale**: `_MEIPASS` is a read-only temp extraction dir; the DB must be writable and
  persistent, so it cannot live there. Absolute paths everywhere satisfy Principle 4.
- **Alternatives considered**: Relative paths (rejected — break under frozen cwd); DB inside
  `_MEIPASS` (rejected — read-only, wiped on exit).

## R6 — Tailwind CSS + Alpine.js + print strategy

- **Decision**: Tailwind CSS compiled once (standalone CLI) to a static stylesheet; Alpine.js v3
  served as a static file; print behavior via Tailwind `print:` variants plus a small
  `@media print` stylesheet hiding `.no-print` sidebar/backgrounds.
- **Rationale**: No client-side build step at runtime (Principle 2); static-file-safe for the
  frozen `.exe` (Principle 4).
- **Alternatives considered**: Node/Vite toolchain (rejected — adds a runtime build step); heavy
  JS framework (rejected — constitution forbids React/Vue/etc.).

## R7 — Date-tolerant matching

- **Decision**: Matching compares amounts with exact `Decimal` equality and NEVER treats dates as
  a blocking condition; a date-gap warning is a UI concern, surfaced but non-blocking.
- **Rationale**: FR-015 / US8: ruthless on amounts, permissive on dates; warnings never block.
- **Alternatives considered**: Date-window rejection (rejected — contradicts spec); no warning at
  all (rejected — spec allows/encourages a warning).
