# Implementation Plan: Phase 1 - Core Reconciliation Engine

**Branch**: `001-core-reconciliation-engine` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-core-reconciliation-engine/spec.md`

## Summary

Build the core reconciliation engine for `total-cb`: a single-enterprise desktop application
(Django 5.1 + SQLite, packaged as a single Windows `.exe`) that imports bank
(`MovimientoBancario`) and internal (`MovimientoInterno`) movements, matches them, and commits
a `Conciliacion` only when the Zero-Sum equation `Sum(Bancario) - Sum(Interno) + Sum(Ajustes)
== 0` holds exactly. All business logic lives in a pure-Python service layer (`services.py`)
wrapped in `@transaction.atomic`; views are thin HTTP adapters. Money uses `decimal.Decimal`
end-to-end (rejecting `float`), and domain constraints use `CheckConstraint(condition=Q(...))`.

## Technical Context

**Language/Version**: Python 3.11+ (Django 5.1+)
**Primary Dependencies**: Django 5.1+, Tailwind CSS (pre-built), Alpine.js v3, PyInstaller
**Storage**: SQLite (single `.db`, absolute path via `sys._MEIPASS` wrapper)
**Testing**: pytest + pytest-django (TDD Red-Green-Refactor)
**Target Platform**: Windows 10/11 (compiled single `.exe`)
**Project Type**: Desktop web application (local Django app, frozen with PyInstaller)
**Performance Goals**: Correctness over speed (single internal user)
**Constraints**: Offline; no runtime client-side build; exact decimal arithmetic
**Scale/Scope**: ~14 entities; thousands of movements per run; two UX surfaces

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle 0 — Language Strictness (CRITICAL)**: PASS — docs in English; identifiers/UI in Spanish.
- **Principle 1 — Database Integrity**: PASS — `CheckConstraint(condition=Q(...))` only; no `check=`.
- **Principle 2 — Integrated Frontend**: PASS — Tailwind CSS + Alpine.js v3 only.
- **Principle 3 — TDD**: PASS — failing tests first, esp. Zero-Sum and Decimal paths.
- **Principle 4 — Desktop Readiness**: PASS — `sys._MEIPASS` wrapper for absolute SQLite/static paths.
- **Principle 5 — Financial Precision & Zero-Sum**: PASS — `Decimal` only; atomic Zero-Sum commit.

## Architectural Components

### 1. Service Layer Abstraction

All domain logic lives in `conciliacion/services.py` as pure Python functions. Views
(`conciliacion/views.py`) MUST NOT contain business logic, arithmetic, or Zero-Sum checks; they
only parse/validate HTTP input, call services, and render templates. Orchestrators
(`commit_reconciliation`, `revert_conciliacion`) are decorated with `@transaction.atomic` so
reconcile→validate→persist is all-or-nothing. Failures raise typed exceptions
(`ZeroSumError`, `AmountMismatchError`, `EstadoInvalidoError`) inside the atomic block to
trigger full rollback (FR-006, SC-001). Matching (`match_movimientos`) and adjustment creation
(`create_ajuste`) are separate pure functions. Signatures: `contracts/service-layer.md`.

### 2. Decimal Enforcement

All monetary columns are `DecimalField` (never `FloatField`). Physical storage uses a single
fixed column (`max_digits=19, decimal_places=8`); the currency-specific precision from
`Moneda.cantidad_decimales` is enforced at the service/validation layer via
`Decimal.quantize(..., rounding=ROUND_HALF_EVEN)` — never `float` (FR-007, FR-009). A boundary
guard rejects `float` outright:

```python
def assert_decimal(value):
    if isinstance(value, float):
        raise TypeError("float is forbidden for money; use Decimal")
    return Decimal(str(value))
```

Only `int`, `str`, and `Decimal` are accepted; serialization converts to/from string.

### 3. Database Constraints

Every domain-rule constraint uses Django 5.1 `Meta.constraints` with
`CheckConstraint(condition=Q(...))`. The legacy `check=` argument is forbidden. Pattern:

```python
from django.db import models
from django.db.models import Q

class Moneda(models.Model):
    cantidad_decimales = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad_decimales__gte=0),
                name="moneda_cantidad_decimales_no_negativa",
            ),
        ]
```

Each constraint carries a stable, explicit `name` for auditable migrations.

### 4. Desktop Pathing Strategy

A single path helper (`totalcb/paths.py`) resolves the base directory: when frozen
(PyInstaller) read-only bundled assets live under `sys._MEIPASS` and the writable data dir is a
per-user location (`%LOCALAPPDATA%\total-cb\`); in dev it is `BASE_DIR`. The SQLite `.db`
resolves to an absolute writable path — dev `BASE_DIR/db.sqlite3`, frozen
`%LOCALAPPDATA%\total-cb\db.sqlite3` (NOT inside `_MEIPASS`, which is read-only/temporary).
Static assets resolve to `sys._MEIPASS/"static"` when frozen, `BASE_DIR/"static"` in dev, via
Django `collectstatic`/`static` tag. Every runtime path goes through the wrapper; no bare
relative paths (Principle 4). Pattern:

```python
def app_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
```

### 5. UI Architecture

Base layout = collapsible sidebar (navigation/filters) + main content via Tailwind utilities.
Split-screen matcher = one template, two side-by-side columns (`lg:grid-cols-2`): left bank,
right internal. Alpine.js v3 (`x-data`, `x-for`, `@click`) holds the reactive working set —
selected rows, candidate matches, "En Consulta" filter toggle, `notas` input, and the date-gap
warning banner; matching stays client-side until commit. Print strategy ("Manual Checking
Report") = a dedicated template whose sidebar/backgrounds are hidden on paper via Tailwind
`print:` variants (`print:hidden`, `print:bg-white`) plus `@media print { .no-print { display:
none !important; } }`. No heavy JS framework (Principle 2); assets static-file-safe (Principle 4).

## Project Structure

### Documentation (this feature)

```text
specs/001-core-reconciliation-engine/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
│   └── service-layer.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
totalcb/                 # Django project
├── settings.py
├── paths.py             # sys._MEIPASS path helper
├── urls.py
└── wsgi.py

conciliacion/            # Django app
├── models.py            # CheckConstraint(condition=Q(...)) models
├── services.py          # pure functions + @transaction.atomic
├── views.py             # thin HTTP handlers
├── templates/conciliacion/
├── static/
└── migrations/

templates/               # base layout + print stylesheet
static/                  # collected Tailwind CSS + Alpine.js

tests/
├── unit/
├── integration/
└── contract/
```

**Structure Decision**: Single Django project + single `conciliacion` app (single-enterprise
desktop scope). Domain logic isolated in `services.py` for TDD without HTTP.

## Complexity Tracking

No constitution violations — all gates pass; no justification required.
