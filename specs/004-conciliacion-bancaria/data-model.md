# Data Model — Conciliación Bancaria (Extracto y Punteo)

Phase 1 output. Identifiers in Spanish (Constitution Principle 0). Money is `Decimal` (2 dp), never `float`.

## New entities

### MovimientoExtracto (bank statement line)

| Field | Type | Notes |
|-------|------|-------|
| `cuenta_bancaria` | FK → `CuentaBancaria`, PROTECT | The reconcilable account |
| `fecha` | `DateField` | Statement posting date |
| `referencia` | `CharField(max_length=100, blank=True)` | Optional external reference |
| `detalle` | `CharField(max_length=255)` | Description |
| `importe` | `ImporteDecimalField(18, 2)` | Signed; net effect; must be non-zero; rejects `float` |
| `origen` | `CharField(choices=manual|importacion, default=manual)` | Provenance for audit |
| `conciliado` | `BooleanField(default=False)` | Set on match; block edit/delete |

Constraints: `CheckConstraint(condition=Q(importe__lt=0) | Q(importe__gt=0))`;
`CheckConstraint(condition=Q(origen__in=["manual","importacion"]))`. Meta `ordering = ["fecha","id"]`.
Sign convention: `importe == libro.debe - libro.haber` (positive = money in / `debe`; negative = money out / `haber`).

### Punteo (the 1:1 link = "conciliado" status)

| Field | Type | Notes |
|-------|------|-------|
| `movimiento_extracto` | FK → `MovimientoExtracto`, PROTECT, `related_name="punteo"` | Unique |
| `movimiento_libro` | FK → `MovimientoLibro`, PROTECT, `related_name="punteo"` | Unique |

Constraints: `UniqueConstraint(fields=["movimiento_extracto"])`;
`UniqueConstraint(fields=["movimiento_libro"])`. Existence of a link **is** the "Conciliado" status; both sides' flags
are kept in sync for fast querying and UI signaling.

### AuditoriaPunteo (audit trail for match/un-match transitions)

Per FR-007, every match (`puntear`) and un-match (`despuntear`) transition MUST be recorded for audit, atomically with
the link/flag change.

| Field | Type | Notes |
|-------|------|-------|
| `fecha_hora` | `DateTimeField(auto_now_add=True)` | When the action happened |
| `accion` | `CharField(max_length=20, choices=puntear|despuntear)` | The transition performed |
| `movimiento_extracto` | FK → `MovimientoExtracto`, PROTECT | The statement side of the pair |
| `movimiento_libro` | FK → `MovimientoLibro`, PROTECT | The ledger side of the pair |
| `usuario` | `CharField(max_length=150, blank=True)` | Acting principal (request user or empty when unavailable) |

Constraints: `CheckConstraint(condition=Q(accion__in=["puntear","despuntear"]))`. Meta
`ordering = ["-fecha_hora", "-id"]` (most recent first). Rows are append-only: no update/delete surface, and `Punteo`
deletion is `on_delete=PROTECT` so an audit row always keeps both sides referencable.

## Existing entity changes

### MovimientoLibro (hardened)

- Reuses the existing `conciliado` boolean as the lock source of truth.
- `delete()` gains a guard: if `self.conciliado` (or a linked `Punteo` exists) raise a typed
  `ConciliadoBloqueadoError`; otherwise proceed and recompute running balances as today.
- The existing balance rule is unchanged: `saldo = saldo_base + debe - haber` (`debe`/`haber` mutual exclusion kept).
- **`tipo_operacion` fallback (FR-008 / "Create Book Entry")**: a book entry materialized from a statement row must
  resolve its `tipo_operacion` deterministically via
  `TipoOperacion.objects.get_or_create(codigo="AJUSTE-BANCARIO", defaults={"nombre": "Ajuste Bancario"})`. This is the
  single canonical default: `get_or_create` guarantees exactly one `TipoOperacion` with
  `codigo="AJUSTE-BANCARIO"` (creating it on first use), so no per-instance ad-hoc `"Ajuste"` string is invented and the
  fallback never depends on a pre-seeded catalog row existing.

## State transitions

- `MovimientoExtracto`: `unmatched (conciliado=False)` ⇄ `matched (conciliado=True)`.
  - `unmatched → matched` only via `puntear` / `crear_asiento_desde_extracto`.
  - `matched → unmatched` only via `despuntear`.
  - `matched` rows are non-editable/non-deletable (both sides).
- `MovimientoLibro`: `conciliado=False ⇄ True`; while `True`, edit/delete are blocked.

## Invariants

- No `Punteo` links rows of different `CuentaBancaria`.
- Every `Punteo` satisfies `extracto.importe == libro.debe - libro.haber` (exact to 2 dp).
- `serialize/deserialize` of money never passes through `float` (enforced by `ImporteDecimalField`).
