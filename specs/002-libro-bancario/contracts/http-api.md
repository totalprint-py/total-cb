# Contract: Libro Bancario HTTP/UI interface

**Branch**: `002-libro-bancario` | **Date**: 2026-09-10

The module's only external interface is its server-rendered HTTP surface. All names are registered
without an `app_name` namespace (matching the existing `conciliacion/urls.py` convention so tests can
`reverse(...)` un-namespaced).

## URL map

| Name | Method | Path | Purpose |
|---|---|---|---|
| `libro_bancario` | GET | `/libro-bancario/` | Master-Detail page: account selector + ledger + entry form |
| `libro_bancario_crear` | POST | `/libro-bancario/movimientos/nuevo/` | Create a `MovimientoLibro` for the selected account |
| `libro_bancario_recalcular` | POST | `/libro-bancario/recalcular/` | Rebuild running balances via `MovimientoLibro.recalcular_saldos` |

## GET `libro_bancario`

- Query param `cuenta` (optional int): preselect a `CuentaBancaria`; if absent/invalid, fall back to
  the first account (or an empty state when no accounts exist).
- Context contract:
  - `cuentas` — all `CuentaBancaria` (with `banco`, `tipo_cuenta`, `moneda`).
  - `cuenta` — the currently selected `CuentaBancaria` (or `None`).
  - `movimientos` — selected account's `MovimientoLibro`, ordered `fecha`/`id` (running `saldo` column).
  - `form` — a fresh `MovimientoLibroForm`.
  - `saldo_inicial` — the selected account's `saldo_inicial` shown as the starting balance.
- Status: 200 (template `conciliacion/libro_bancario.html`).

## POST `libro_bancario_crear`

- `cuenta` (required) identifies the target `CuentaBancaria` and is supplied **out-of-band** via
  the request URL (query param or path) or a hidden input — NOT as a `MovimientoLibroForm` field.
  The view resolves it with `get_object_or_404(CuentaBancaria, pk=cuenta_id)` and assigns it to
  `form.instance.cuenta` before `form.save()`.
- Form fields (from `MovimientoLibroForm`): `fecha`, `tipo_operacion`, `detalle`, `debe`, `haber`.
- Success: persists the movement; `MovimientoLibro.save()` computes `saldo`; redirect 302 →
  `libro_bancario?cuenta=<id>`.
- Failure (invalid form / FR-007 violation): re-render `libro_bancario.html` with the selected
  account's `movimientos` and the bound `form` showing Spanish inline errors (status 200).
- Non-POST → 405 (consistent with the existing `emparejar_movimientos` pattern).

## POST `libro_bancario_recalcular`

- Field: `cuenta` (required).
- Behavior: calls `MovimientoLibro.recalcular_saldos(cuenta_id)`; redirect 302 → `libro_bancario?cuenta=<id>`.
- Missing/invalid `cuenta`: 404 (`get_object_or_404`).
- Non-POST → 405.

## Rendering / accessibility contract

- Spanish UI strings; `lang="es"`.
- Horizontal entry form tab order: `fecha` → `tipo_operacion` → `detalle` → `debe` → `haber` → submit.
- `Enter` submits the form natively; `autofocus` on the first field; amounts use `inputmode="decimal"`.
- High contrast: dark table header (`table-dark`), dark master panel (`bg-dark`), primary action
  (`btn-primary`), and a visible `:focus-visible` outline for keyboard users.
