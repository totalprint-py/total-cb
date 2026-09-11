# Quickstart & Validation Guide: Core Reconciliation Engine

**Branch**: `001-core-reconciliation-engine` | **Date**: 2026-09-04

Runnable scenarios that prove the feature end-to-end once implemented. This is a run guide;
implementation details belong to `tasks.md` and the implementation phase.

## Prerequisites

- Python 3.11+, Django 5.1+, pytest + pytest-django.
- SQLite available locally (no server).

## Setup

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## Test / run

```text
pytest                          # full TDD suite (unit, integration, contract)
python manage.py runserver      # local dev server (dev path resolution)
```

## Validation scenarios

1. **Zero-Sum commit (US1)**: import a controlled bank/internal set whose totals balance; run
   reconciliation; assert a `Conciliacion` + matched details persist and the equation holds.
2. **Zero-Sum rollback (US1/FR-006)**: introduce a one-cent imbalance; assert the commit is
   rejected and NOTHING persists (no `Conciliacion`, no details).
3. **Decimal enforcement (FR-007/FR-009)**: pass a `float` to a service function; assert
   `TypeError`. Verify a value with excess decimals is quantized to `cantidad_decimales`
   deterministically.
4. **Date tolerance (US8/FR-015)**: match two movements with identical amounts but dates weeks
   apart; assert success (with optional warning). Match a one-cent mismatch; assert rejection.
5. **"En Consulta" flag (US6/FR-013)**: flag a pending bank movement; assert it stays in the
   pending list and is isolated visually.
6. **Notes (US7/FR-014)**: add/edit/clear a `notas` value; assert amounts/dates/state are
   untouched.
7. **Duplicate import (FR-012)**: import the same `LoteImportacion` twice; assert the second is
   rejected.
8. **Revert unlock (US5/FR-010)**: edit a committed detail (rejected); revert the conciliacion;
   assert records unlock.

## Expected outcomes

All scenarios pass without floating-point rounding and without partial persistence on failure.
