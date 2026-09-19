"""Capa de agregación de reportes del Libro Bancario (Fase 2 — GREEN).

Implementa la proyección de solo lectura descrita en
``specs/003-reportes-libro-bancario/data-model.md``:

* la excepción tipada ``RangoFechasInvalidoError``;
* el tipo de resultado congelado ``ReporteLibro``;
* la función pura ``generar_reporte_libro``, fuente única del dato canónico
  consumido por los cuatro formatos de salida (FR-007/FR-009).

Los importes monetarios se manejan exclusivamente con ``decimal.Decimal``
(FR-010) y la llamada no realiza ninguna escritura (FR-009).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from conciliacion.models import CuentaBancaria, MovimientoLibro


# ---------------------------------------------------------------------------
# Error de dominio
# ---------------------------------------------------------------------------


class RangoFechasInvalidoError(Exception):
    """Error de dominio: el rango de fechas del reporte no es válido (FR-008)."""


# ---------------------------------------------------------------------------
# Tipo de resultado congelado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReporteLibro:
    """Resultado congelado de la agregación del Libro Bancario.

    Expone la proyección de solo lectura definida en data-model.md: ``cuenta``,
    ``fecha_desde``/``fecha_hasta`` (límites inclusivos), ``movimientos``
    (renglones ordenados por ``fecha`` e ``id``), el saldo de apertura del
    periodo, los totales del debe/haber y el saldo final calculado.
    """

    cuenta: CuentaBancaria
    fecha_desde: date
    fecha_hasta: date
    movimientos: list[MovimientoLibro]
    saldo_inicial_periodo: Decimal
    total_debe: Decimal
    total_haber: Decimal
    saldo_final: Decimal


# ---------------------------------------------------------------------------
# Agregación (read-only)
# ---------------------------------------------------------------------------


def generar_reporte_libro(*, cuenta, fecha_desde, fecha_hasta) -> ReporteLibro:
    """Agrega los movimientos del libro de una cuenta para un rango inclusivo.

    Reglas de derivación (data-model.md):

    1. Filtra por ``cuenta`` + ``fecha__gte=fecha_desde``/``fecha__lte=fecha_hasta``
       ordenando por ``fecha`` e ``id`` (FR-002).
    2. El saldo inicial del periodo es el ``saldo`` del último movimiento con
       ``fecha < fecha_desde``; si no existe, ``cuenta.saldo_inicial`` (FR-004).
    3. Totales y saldo final: ``total_debe = Σ debe``, ``total_haber = Σ haber``
       y ``saldo_final = saldo_inicial_periodo + total_debe - total_haber`` (FR-005).

    Error: ``RangoFechasInvalidoError`` si las fechas no son ``date`` o si
    ``fecha_desde > fecha_hasta`` (FR-008). La función es de solo lectura (FR-009).
    """
    _validar_rango(fecha_desde, fecha_hasta)

    movimientos = list(
        MovimientoLibro.objects.filter(
            cuenta=cuenta,
            fecha__gte=fecha_desde,
            fecha__lte=fecha_hasta,
        ).order_by("fecha", "id")
    )

    saldo_inicial_periodo = _calcular_saldo_inicial_periodo(cuenta, fecha_desde)

    total_debe = sum((movimiento.debe for movimiento in movimientos), Decimal("0.00"))
    total_haber = sum((movimiento.haber for movimiento in movimientos), Decimal("0.00"))
    saldo_final = saldo_inicial_periodo + total_debe - total_haber

    return ReporteLibro(
        cuenta=cuenta,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        movimientos=movimientos,
        saldo_inicial_periodo=saldo_inicial_periodo,
        total_debe=total_debe,
        total_haber=total_haber,
        saldo_final=saldo_final,
    )


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _validar_rango(fecha_desde, fecha_hasta) -> None:
    """Valida que el rango esté formado por fechas válidas y ordenadas (FR-008)."""
    if not isinstance(fecha_desde, date) or not isinstance(fecha_hasta, date):
        raise RangoFechasInvalidoError(
            "El rango de fechas es inválido: 'desde' y 'hasta' deben ser "
            "fechas válidas."
        )
    if fecha_desde > fecha_hasta:
        raise RangoFechasInvalidoError(
            "El rango de fechas es inválido: la fecha 'desde' no puede ser "
            "posterior a la fecha 'hasta'."
        )


def _calcular_saldo_inicial_periodo(cuenta, fecha_desde) -> Decimal:
    """Devuelve el saldo de apertura del rango seleccionado (FR-004).

    Es el ``saldo`` del último movimiento anterior al rango; si no existe
    ningún movimiento con ``fecha < fecha_desde``, usa ``cuenta.saldo_inicial``.
    """
    movimiento_anterior = (
        MovimientoLibro.objects.filter(cuenta=cuenta, fecha__lt=fecha_desde)
        .order_by("fecha", "id")
        .last()
    )
    if movimiento_anterior is not None:
        return movimiento_anterior.saldo
    return cuenta.saldo_inicial
