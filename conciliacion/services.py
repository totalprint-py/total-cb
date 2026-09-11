"""Capa de servicios del motor de conciliación (Fase 5 — GREEN).

Implementa la frontera de dominio descrita en
``specs/001-core-reconciliation-engine/contracts/service-layer.md``:

* Excepciones tipadas: ``ZeroSumError``, ``AmountMismatchError``,
  ``EstadoInvalidoError`` y la advertencia no bloqueante ``DateGapWarning``.
* Funciones puras: ``assert_decimal``, ``quantize_to_moneda``,
  ``flag_en_consulta``, ``set_nota`` y ``create_ajuste``.
* Orquestadores transaccionales: ``match_movimientos``,
  ``commit_reconciliation`` y ``revert_conciliacion``.

Los importes monetarios solo admiten ``decimal.Decimal`` (FR-007); cualquier
``float`` se rechaza en la frontera con ``TypeError``. Toda la lógica, los
nombres y los mensajes están en español.
"""
from __future__ import annotations

import warnings
from decimal import ROUND_HALF_EVEN, Decimal

from django.db import transaction
from django.db.models import Sum

from conciliacion.models import (
    AjusteConciliacion,
    Conciliacion,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
)

# Umbral (en días) a partir del cual una diferencia de fechas entre dos
# movimientos emparejados se considera "brecha extrema" y genera una advertencia
# no bloqueante ``DateGapWarning`` (FR-015 / US8: permisivo en fechas, nunca
# bloquea el emparejamiento).
UMBRAL_BRECHA_FECHAS_DIAS = 30


# ---------------------------------------------------------------------------
# Excepciones tipadas del dominio
# ---------------------------------------------------------------------------


class ErrorConciliacion(Exception):
    """Base común para los errores de dominio del motor de conciliación."""


class ZeroSumError(ErrorConciliacion):
    """La ecuación de suma cero no se cumple (FR-006 / SC-001)."""


class AmountMismatchError(ErrorConciliacion):
    """Los importes de los movimientos no coinciden de forma exacta (FR-015)."""


class EstadoInvalidoError(ErrorConciliacion):
    """La conciliación no está en el estado requerido por la operación."""


class DateGapWarning(Warning):
    """Advertencia no bloqueante por brecha de fechas entre movimientos."""


# ---------------------------------------------------------------------------
# Funciones puras de frontera
# ---------------------------------------------------------------------------


def assert_decimal(valor) -> Decimal:
    """Convierte ``valor`` a ``Decimal`` rechazando ``float`` (FR-007).

    Pre: ``valor`` es ``int``, ``str`` o ``Decimal``.
    Post: devuelve ``Decimal(valor)``.
    Error: ``TypeError`` si ``valor`` es ``float``.
    """
    if isinstance(valor, float):
        raise TypeError(
            "Los importes monetarios no admiten float; use decimal.Decimal."
        )
    return Decimal(valor)


def quantize_to_moneda(importe, moneda) -> Decimal:
    """Redondea un importe a la precisión decimal de la moneda (FR-009).

    Aplica ``Decimal.quantize`` con ``ROUND_HALF_EVEN`` usando la cantidad de
    decimales definida en ``Moneda.cantidad_decimales``.
    """
    importe_decimal = assert_decimal(importe)
    cantidad_decimales = int(moneda.cantidad_decimales)
    quantum = Decimal(1).scaleb(-cantidad_decimales)
    return importe_decimal.quantize(quantum, rounding=ROUND_HALF_EVEN)


def flag_en_consulta(*, movimiento_bancario, en_consulta: bool) -> None:
    """Activa o desactiva la bandera "En Consulta" (FR-013).

    Solo cambia ``en_consulta``; el movimiento permanece en la lista pendiente.
    """
    movimiento_bancario.en_consulta = en_consulta
    movimiento_bancario.save(update_fields=["en_consulta"])


def set_nota(*, movimiento, texto: str) -> None:
    """Asigna y persiste la nota de texto libre de un movimiento (FR-014).

    Acepta ``MovimientoBancario`` o ``MovimientoInterno``; no altera importe,
    fecha ni estado.
    """
    movimiento.notas = texto
    movimiento.save(update_fields=["notas"])


def create_ajuste(*, conciliacion, concepto_ajuste, importe) -> AjusteConciliacion:
    """Crea y persiste un ajuste de conciliación (FR-008).

    Pre: ``importe`` es ``Decimal``; ``conciliacion`` está en estado borrador.
    Error: ``TypeError`` para ``float``; ``EstadoInvalidoError`` si no es borrador.
    """
    importe_decimal = assert_decimal(importe)
    if conciliacion.estado != Conciliacion.ESTADO_BORRADOR:
        raise EstadoInvalidoError(
            "Solo se pueden crear ajustes en una conciliación en estado borrador."
        )
    return AjusteConciliacion.objects.create(
        conciliacion=conciliacion,
        concepto_ajuste=concepto_ajuste,
        importe=importe_decimal,
    )


# ---------------------------------------------------------------------------
# Orquestadores transaccionales
# ---------------------------------------------------------------------------


def _obtener_o_crear_borrador(cuenta_bancaria, bancario, interno) -> Conciliacion:
    """Devuelve el borrador vigente de la cuenta o lo crea si no existe.

    Nota arquitectónica: ``match_movimientos`` no recibe la conciliación como
    parámetro; la deriva de la cuenta bancaria del movimiento bancario. Si no
    existe un borrador, se crea uno derivando el rango de fechas de los
    movimientos emparejados.
    """
    borrador = (
        Conciliacion.objects.filter(
            cuenta_bancaria=cuenta_bancaria,
            estado=Conciliacion.ESTADO_BORRADOR,
        )
        .order_by("pk")
        .first()
    )
    if borrador is not None:
        return borrador
    return Conciliacion.objects.create(
        cuenta_bancaria=cuenta_bancaria,
        estado=Conciliacion.ESTADO_BORRADOR,
        fecha_desde=min(bancario.fecha, interno.fecha),
        fecha_hasta=max(bancario.fecha, interno.fecha),
    )


@transaction.atomic
def match_movimientos(*, bancario, interno):
    """Empareja dos movimientos de importe exacto (FR-015).

    Post: crea el par de detalles (bancario e interno) en la misma conciliación
    borrador. Error: ``AmountMismatchError`` si los importes difieren (incluso
    un centavo). Advertencia: ``DateGapWarning`` no bloqueante si las fechas
    difieren más allá del umbral configurado.
    """
    if bancario.importe != interno.importe:
        raise AmountMismatchError(
            "No se puede emparejar: los importes difieren "
            f"({bancario.importe} vs {interno.importe})."
        )

    if abs((bancario.fecha - interno.fecha).days) > UMBRAL_BRECHA_FECHAS_DIAS:
        warnings.warn(
            "Los movimientos emparejados presentan una brecha de fechas "
            "superior al umbral permitido.",
            DateGapWarning,
            stacklevel=2,
        )

    conciliacion = _obtener_o_crear_borrador(
        bancario.cuenta_bancaria, bancario, interno
    )

    detalle_bancaria = DetalleConciliacionBancaria.objects.create(
        conciliacion=conciliacion,
        movimiento_bancario=bancario,
    )
    detalle_interna = DetalleConciliacionInterna.objects.create(
        conciliacion=conciliacion,
        movimiento_interno=interno,
    )
    return detalle_bancaria, detalle_interna


@transaction.atomic
def commit_reconciliation(*, conciliacion) -> None:
    """Compromete una conciliación validando la ecuación de suma cero (FR-006).

    Regla: ``Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0`` exacto. Si no se
    cumple, lanza ``ZeroSumError`` y revierte cualquier cambio (rollback atómico).
    """
    if conciliacion.estado != Conciliacion.ESTADO_BORRADOR:
        raise EstadoInvalidoError(
            "Solo se puede comprometer una conciliación en estado borrador."
        )

    total_bancario = (
        DetalleConciliacionBancaria.objects.filter(conciliacion=conciliacion)
        .aggregate(total=Sum("movimiento_bancario__importe"))["total"]
        or Decimal("0")
    )
    total_interno = (
        DetalleConciliacionInterna.objects.filter(conciliacion=conciliacion)
        .aggregate(total=Sum("movimiento_interno__importe"))["total"]
        or Decimal("0")
    )
    total_ajustes = (
        AjusteConciliacion.objects.filter(conciliacion=conciliacion)
        .aggregate(total=Sum("importe"))["total"]
        or Decimal("0")
    )

    if total_bancario - total_interno + total_ajustes != Decimal("0"):
        raise ZeroSumError(
            "No se puede comprometer: la ecuación de suma cero no se cumple "
            f"(bancario={total_bancario}, interno={total_interno}, "
            f"ajustes={total_ajustes})."
        )

    conciliacion.estado = Conciliacion.ESTADO_COMPROMETIDA
    conciliacion.save(update_fields=["estado"])


@transaction.atomic
def revert_conciliacion(*, conciliacion) -> None:
    """Revierte una conciliación comprometida sin eliminar sus detalles (FR-010).

    Post: estado → ``reverted``; los registros enlazados quedan desbloqueados.
    Error: ``EstadoInvalidoError`` si no está comprometida (borrador o ya revertida).
    """
    if conciliacion.estado != Conciliacion.ESTADO_COMPROMETIDA:
        raise EstadoInvalidoError(
            "Solo se puede revertir una conciliación comprometida."
        )

    conciliacion.estado = Conciliacion.ESTADO_REVERTIDA
    conciliacion.save(update_fields=["estado"])

