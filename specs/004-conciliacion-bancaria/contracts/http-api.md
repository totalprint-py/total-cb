# HTTP API Contract — Conciliación Bancaria (Extracto y Punteo)

All names are un-namespaced Django URL names (existing convention). Actions mutating state are POST; successful POSTs
redirect (302) with a `messages` flash; domain errors return 400 with a Spanish message. GET render list/form pages.

## Endpoints

| URL name | Method | Path | Behaviour |
|----------|--------|------|-----------|
| `extracto_list` | GET | `/extracto/` | List `MovimientoExtracto` (account filter optional), lock indicators |
| `extracto_create` | GET/POST | `/extracto/nuevo/` | Manual create form |
| `extracto_update` | GET/POST | `/extracto/<pk>/editar/` | Edit unmatched row; 400 if `conciliado` |
| `extracto_delete` | POST | `/extracto/<pk>/eliminar/` | Delete unmatched row; 400 if `conciliado` |
| `extracto_importar` | GET/POST | `/extracto/importar/` | Upload `.xlsx`/`.csv` for a `CuentaBancaria`; all-or-nothing |
| `punteo` | GET | `/punteo/` | Dual-list of unmatched extracto vs libro for a selected account |
| `puntear` | POST | `/punteo/puntear/` | `extracto_id` + `libro_id`; link + mark `conciliado`, and atomically write an `AuditoriaPunteo` (accion=`puntear`) row; 400 on mismatch |
| `despuntear` | POST | `/punteo/despuntear/<extracto_id>/` | Remove link, reset both flags, and atomically write an `AuditoriaPunteo` (accion=`despuntear`) row |
| `crear_asiento_extracto` | GET/POST | `/extracto/<pk>/crear-asiento/` | Pre-filled form; POST creates libro + links both, and atomically write an `AuditoriaPunteo` (accion=`puntear`) row |

## Request/response details

- `puntear` POST body: `extracto_id`, `libro_id`. Validates same `CuentaBancaria`; on amount mismatch returns 400 with
  the Spanish message `"No se puede puntear: los importes difieren (…)."`.
- `extracto_importar` POST multipart: `cuenta` (account pk) + `archivo` (uploaded file). On success: 302 to
  `extracto_list` with a summary flash (`"Se importaron N movimientos."`). On failure: re-render the form with a list of
  per-row errors and **no** persisted rows.
- `crear_asiento_extracto` GET pre-fills `fecha`, `detalle` and the sign-mapped `debe`/`haber` from the
  `MovimientoExtracto`; POST persists atomically and redirects back to `punteo`.
- Immutability errors return 400 (views) with `"El movimiento conciliado no puede editarse ni eliminarse."`.

## Status code summary

- `200` — page render.
- `302` — successful mutation (CRUD/match/unmatch/import/create-asiento).
- `400` — validation or domain error (mismatch, locked record, invalid import).
- `404` — unknown pk.
- `405` — non-allowed method on mutation-only endpoints.
