# Import Format Contract — Conciliación Bancaria (Extracto y Punteo)

Defines the acceptable `.xlsx`/`.csv` shapes consumed by `extracto_importar`. The account is selected in the upload
form (not derived from the file).

## Canonical header row

```text
fecha,referencia,detalle,importe
```

| Column | Required | Type / format | Semantics |
|--------|----------|---------------|-----------|
| `fecha` | yes | `YYYY-MM-DD` (or an ISO-parsable date) | Statement posting date |
| `referencia` | no | text | External bank reference (blank allowed) |
| `detalle` | yes | text (≤255 chars) | Description |
| `importe` | yes | signed `Decimal` (2 dp) | Positive = money in (`debe`); negative = money out (`haber`); non-zero |

## Accepted alternatives

- The parser accepts the Spanish aliases `fecha`(`date`), `detalle`(`descripcion`,`concepto`), and `importe`
  (`monto`). `referencia` aliases: `ref`,`numero`.
- If the file instead uses two columns `debe` and `haber`, the parser computes `importe = debe - haber` (both columns
  must otherwise satisfy the same non-negative, mutual-exclusion rules as `MovimientoLibro`).

## Benchmark fixture — `1 Continental Guaranies.xlsx` (sheet `CONTINENTAL`)

The repo-root benchmark fixture uses the two-column layout with this real header:

```text
FECHA, OPERACIÓN, DETALLE, DEBE, HABER, SALDO
```

| Bank column | Normalized to | Rule |
|-------------|---------------|------|
| `FECHA` | `fecha` | case-insensitive header match |
| `OPERACIÓN` | — (ignored) | extra descriptive column, not persisted |
| `DETALLE` | `detalle` | case-insensitive; the statement description |
| `DEBE` | money in | `importe = +DEBE` |
| `HABER` | money out | `importe = -HABER` |
| `SALDO` | — (ignored) | running balance, not imported |

Sampled rows pin the sign mapping: `Deposito BELLINI` → `DEBE = 980,000` (money in, `importe = +980,000`) and
`EGRESO COMPRA $ 20,000*6.010` → `HABER = 120,200,000` (money out, `importe = -120,200,000`); the running balance
follows `SALDO = SALDO_prev + DEBE - HABER`. Thus `importe = DEBE - HABER` reproduces the canonical signed amount with
**no sign inversion**: bank `DEBE` = `MovimientoLibro.debe` (money in) and bank `HABER` = `MovimientoLibro.haber`
(money out).

The parser MUST additionally: (1) match headers case-insensitively; (2) ignore the extra `OPERACIÓN` and `SALDO`
columns; (3) skip the `Saldo Anterior` preamble row (opening balance booked under `HABER`) and the footer totals row
(`DEBE=207,500,227`, `HABER=199,405,356`, `SALDO=8,094,871`) so no phantom movement is imported. Pinned numbers become
import tests in `tests/unit/test_extracto_importadores.py`.

## Validation & error model

- Missing/extra header, empty file, or a row with a non-`Decimal`/`float`/zero `importe`, or an invalid `fecha`, marks
  the **whole import** invalid: the transaction rolls back and the form reports the row number + reason for each error.
- `float` values are rejected before any `Decimal` coercion (per `ImporteDecimalField` / Constitution Principle 5).
- Amounts are quantized to the account currency precision (2 dp) with `ROUND_HALF_EVEN` via `quantize_to_moneda`.
- Duplicate statement rows are not deduplicated automatically in v1; the operator resolves them in the punteo screen
  (documented assumption, see `data-model.md`).
