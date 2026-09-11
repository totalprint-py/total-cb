"""Pruebas unitarias de las funciones matemáticas y de orquestación de la capa
de servicios (Fase 4 — RED, segunda mitad).

Cubre exclusivamente las funciones de núcleo definidas en
``specs/001-core-reconciliation-engine/contracts/service-layer.md``:

* ``match_movimientos``: emparejamiento exacto de importes (FR-015).
* ``commit_reconciliation``: validación de la ecuación de suma cero (FR-006).
* ``revert_conciliacion``: desbloqueo de registros comprometidos (FR-010).

Verifica explícitamente la regla de suma cero
``Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0``, los estados de éxito y
que las excepciones ``ZeroSumError``, ``AmountMismatchError`` y
``EstadoInvalidoError`` provoquen el rollback y detengan el proceso.

Estas pruebas se ejecutan contra ``conciliacion/services.py``, que todavía no
existe; por eso deben fallar en rojo (RED) por error de importación. Todas las
descripciones, funciones y variables están en español.
"""
from __future__ import annotations

import warnings
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from conciliacion.models import (
    AjusteConciliacion,
    Conciliacion,
    CuentaBancaria,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
    LoteImportacion,
    MovimientoBancario,
    MovimientoInterno,
)
from conciliacion.services import (
    AmountMismatchError,
    DateGapWarning,
    EstadoInvalidoError,
    ZeroSumError,
    commit_reconciliation,
    match_movimientos,
    revert_conciliacion,
)

# Constantes de fechas reutilizadas en el montaje de escenarios.
FECHA_IMPORTACION = timezone.make_aware(datetime(2026, 9, 5, 10, 30, 0))
FECHA_DESDE = date(2026, 9, 1)
FECHA_HASTA = date(2026, 9, 30)
FECHA_MOVIMIENTO = date(2026, 9, 5)
# Fecha extrema, meses después, para forzar la advertencia de brecha de fechas.
FECHA_BRECHA = date(2026, 12, 31)


def _crear_lote(**sobrescribir):
    valores = {"fuente": "BANCO-X.csv", "fecha_importacion": FECHA_IMPORTACION}
    valores.update(sobrescribir)
    return LoteImportacion.objects.create(**valores)


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    valores = {
        "numero_cuenta": "0001-2345-6789",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


def _crear_movimiento_bancario(
    cuenta_bancaria, lote, tipo_operacion, moneda, importe, fecha, **sobrescribir
):
    valores = {
        "importe": importe,
        "fecha": fecha,
        "cuenta_bancaria": cuenta_bancaria,
        "lote_importacion": lote,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoBancario.objects.create(**valores)


def _crear_movimiento_interno(lote, tipo_operacion, moneda, importe, fecha, **sobrescribir):
    valores = {
        "importe": importe,
        "fecha": fecha,
        "lote_importacion": lote,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoInterno.objects.create(**valores)


def _crear_conciliacion(cuenta_bancaria, estado="draft", **sobrescribir):
    valores = {
        "estado": estado,
        "fecha_desde": FECHA_DESDE,
        "fecha_hasta": FECHA_HASTA,
        "cuenta_bancaria": cuenta_bancaria,
    }
    valores.update(sobrescribir)
    return Conciliacion.objects.create(**valores)


def _crear_detalle_bancaria(conciliacion, movimiento_bancario):
    return DetalleConciliacionBancaria.objects.create(
        conciliacion=conciliacion,
        movimiento_bancario=movimiento_bancario,
    )


def _crear_detalle_interna(conciliacion, movimiento_interno):
    return DetalleConciliacionInterna.objects.create(
        conciliacion=conciliacion,
        movimiento_interno=movimiento_interno,
    )


def _crear_ajuste(conciliacion, concepto_ajuste, importe):
    return AjusteConciliacion.objects.create(
        conciliacion=conciliacion,
        concepto_ajuste=concepto_ajuste,
        importe=importe,
    )


@pytest.fixture
def entorno(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Devuelve las entidades de catálogo base más una cuenta y un lote listos."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)
    lote = _crear_lote()
    return {
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
        "tipo_operacion": tipo_operacion,
        "cuenta_bancaria": cuenta_bancaria,
        "lote": lote,
    }

class TestMatchMovimientos:
    """Pruebas de ``match_movimientos`` (emparejamiento exacto de importes, FR-015).

    El contrato no recibe la conciliación como parámetro; la función la deriva a
    partir de la cuenta bancaria del movimiento bancario (su borrador vigente).
    """

    @pytest.mark.django_db
    def test_coincidencia_exacta_crea_el_par_de_detalles(self, entorno):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        resultado = match_movimientos(bancario=bancario, interno=interno)

        assert isinstance(resultado, tuple)
        assert len(resultado) == 2
        detalle_bancaria, detalle_interna = resultado

        assert isinstance(detalle_bancaria, DetalleConciliacionBancaria)
        assert isinstance(detalle_interna, DetalleConciliacionInterna)
        assert detalle_bancaria.pk is not None
        assert detalle_interna.pk is not None
        assert detalle_bancaria.movimiento_bancario_id == bancario.pk
        assert detalle_interna.movimiento_interno_id == interno.pk
        # Ambos detalles deben pertenecer a la misma conciliación (el borrador).
        assert detalle_bancaria.conciliacion_id == conciliacion.pk
        assert detalle_interna.conciliacion_id == conciliacion.pk

    @pytest.mark.django_db
    def test_diferencia_de_un_centavo_lanza_amountmismatcherror(self, entorno):
        _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.01"),
            fecha=FECHA_MOVIMIENTO,
        )
        with pytest.raises(AmountMismatchError):
            match_movimientos(bancario=bancario, interno=interno)

        assert DetalleConciliacionBancaria.objects.count() == 0
        assert DetalleConciliacionInterna.objects.count() == 0

    @pytest.mark.django_db
    def test_diferencia_significativa_tambien_lanza_amountmismatcherror(self, entorno):
        _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("50.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        with pytest.raises(AmountMismatchError):
            match_movimientos(bancario=bancario, interno=interno)

        assert DetalleConciliacionBancaria.objects.count() == 0
        assert DetalleConciliacionInterna.objects.count() == 0

    @pytest.mark.django_db
    def test_brecha_extrema_de_fechas_emite_advertencia_no_bloqueante(self, entorno):
        _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_BRECHA,
        )
        with pytest.warns(DateGapWarning):
            detalle_bancaria, detalle_interna = match_movimientos(
                bancario=bancario, interno=interno
            )

        assert detalle_bancaria.pk is not None
        assert detalle_interna.pk is not None

    @pytest.mark.django_db
    def test_fechas_cercanas_no_emiten_advertencia(self, entorno):
        _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", DateGapWarning)
            detalle_bancaria, detalle_interna = match_movimientos(
                bancario=bancario, interno=interno
            )

        assert detalle_bancaria.pk is not None
        assert detalle_interna.pk is not None

class TestCommitReconciliation:
    """Pruebas de ``commit_reconciliation`` (ecuación de suma cero, FR-006).

    Verifica ``Sum(Bancario) - Sum(Interno) + Sum(Ajustes) == 0`` antes de
    comprometer la conciliación y que un desequilibrio lance ``ZeroSumError``
    dejando el estado sin cambios (rollback).
    """

    @pytest.mark.django_db
    def test_totales_balanceados_comprometen(self, entorno):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        _crear_detalle_bancaria(conciliacion, bancario)
        _crear_detalle_interna(conciliacion, interno)

        resultado = commit_reconciliation(conciliacion=conciliacion)

        assert resultado is None
        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_COMPROMETIDA

    @pytest.mark.django_db
    def test_ajustes_compensan_el_desequilibrio(self, entorno, concepto_ajuste_factory):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("80.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        _crear_detalle_bancaria(conciliacion, bancario)
        _crear_detalle_interna(conciliacion, interno)
        # 100 - 80 + (-20) == 0
        _crear_ajuste(conciliacion, concepto_ajuste_factory(), Decimal("-20.00"))

        commit_reconciliation(conciliacion=conciliacion)

        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_COMPROMETIDA

    @pytest.mark.django_db
    def test_desequilibrio_de_un_centavo_lanza_zerosumerror(self, entorno):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.01"),
            fecha=FECHA_MOVIMIENTO,
        )
        _crear_detalle_bancaria(conciliacion, bancario)
        _crear_detalle_interna(conciliacion, interno)

        with pytest.raises(ZeroSumError):
            commit_reconciliation(conciliacion=conciliacion)

        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_BORRADOR

    @pytest.mark.django_db
    def test_ajuste_insuficiente_lanza_zerosumerror_y_hace_rollback(
        self, entorno, concepto_ajuste_factory
    ):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        interno = _crear_movimiento_interno(
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("80.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        _crear_detalle_bancaria(conciliacion, bancario)
        _crear_detalle_interna(conciliacion, interno)
        # 100 - 80 + (-19.99) == 0.01 -> desequilibrio.
        _crear_ajuste(conciliacion, concepto_ajuste_factory(), Decimal("-19.99"))

        with pytest.raises(ZeroSumError):
            commit_reconciliation(conciliacion=conciliacion)

        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_BORRADOR
        # Los detalles y el ajuste no se eliminan: solo se revierte el cambio.
        assert DetalleConciliacionBancaria.objects.count() == 1
        assert DetalleConciliacionInterna.objects.count() == 1
        assert AjusteConciliacion.objects.count() == 1

    @pytest.mark.django_db
    def test_conciliacion_vacia_se_compromete(self, entorno):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])

        commit_reconciliation(conciliacion=conciliacion)

        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_COMPROMETIDA

class TestRevertConciliacion:
    """Pruebas de ``revert_conciliacion`` (desbloqueo de registros, FR-010)."""

    @pytest.mark.django_db
    def test_comprometida_se_revierte(self, entorno):
        conciliacion = _crear_conciliacion(
            entorno["cuenta_bancaria"], estado=Conciliacion.ESTADO_COMPROMETIDA
        )
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        _crear_detalle_bancaria(conciliacion, bancario)

        resultado = revert_conciliacion(conciliacion=conciliacion)

        assert resultado is None
        conciliacion.refresh_from_db()
        assert conciliacion.estado == Conciliacion.ESTADO_REVERTIDA

    @pytest.mark.django_db
    def test_no_elimina_los_detalles_al_revertir(self, entorno):
        conciliacion = _crear_conciliacion(
            entorno["cuenta_bancaria"], estado=Conciliacion.ESTADO_COMPROMETIDA
        )
        bancario = _crear_movimiento_bancario(
            entorno["cuenta_bancaria"],
            entorno["lote"],
            entorno["tipo_operacion"],
            entorno["moneda"],
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
        )
        detalle = _crear_detalle_bancaria(conciliacion, bancario)

        revert_conciliacion(conciliacion=conciliacion)

        # Desbloquea (no borra): el detalle sigue existiendo tras la reversión.
        assert DetalleConciliacionBancaria.objects.filter(pk=detalle.pk).exists()

    @pytest.mark.django_db
    def test_borrador_lanza_estadoinvalidoerror(self, entorno):
        conciliacion = _crear_conciliacion(entorno["cuenta_bancaria"])

        with pytest.raises(EstadoInvalidoError):
            revert_conciliacion(conciliacion=conciliacion)

    @pytest.mark.django_db
    def test_segunda_reversion_lanza_estadoinvalidoerror(self, entorno):
        conciliacion = _crear_conciliacion(
            entorno["cuenta_bancaria"], estado=Conciliacion.ESTADO_COMPROMETIDA
        )
        revert_conciliacion(conciliacion=conciliacion)

        with pytest.raises(EstadoInvalidoError):
            revert_conciliacion(conciliacion=conciliacion)
