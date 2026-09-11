"""Pruebas de validación de ``MovimientoLibro`` (FR-007) — RED.

Verifican que ``MovimientoLibro.full_clean()`` rechace importes negativos en
``debe``/``haber`` y exija al menos un importe distinto de cero. Todas las
validaciones se describen en español.

Estado esperado al escribir estas pruebas: ``MovimientoLibro`` aún no declara
``clean()``, por lo que ``full_clean()`` debe aceptar importes inválidos y las
pruebas fallan en rojo (RED).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from conciliacion.models import CuentaBancaria, MovimientoLibro

FECHA = date(2026, 9, 5)


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` de apoyo."""
    valores = {
        "numero_cuenta": "0001-2345-6789",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


@pytest.fixture
def cuenta(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)


@pytest.fixture
def tipo_operacion(tipo_operacion_factory):
    """Devuelve un ``TipoOperacion`` persistido."""
    return tipo_operacion_factory()


class TestMovimientoLibroFullClean:
    """Pruebas de la validación FR-007 vía ``full_clean()``."""

    @pytest.mark.django_db
    def test_debe_negativo_es_invalido(self, cuenta, tipo_operacion):
        """Un ``debe`` negativo debe lanzar ``ValidationError``."""
        movimiento = MovimientoLibro(
            cuenta=cuenta,
            fecha=FECHA,
            tipo_operacion=tipo_operacion,
            detalle="Depósito inválido",
            debe=Decimal("-10.00"),
            haber=Decimal("0.00"),
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_haber_negativo_es_invalido(self, cuenta, tipo_operacion):
        """Un ``haber`` negativo debe lanzar ``ValidationError``."""
        movimiento = MovimientoLibro(
            cuenta=cuenta,
            fecha=FECHA,
            tipo_operacion=tipo_operacion,
            detalle="Depósito inválido",
            debe=Decimal("0.00"),
            haber=Decimal("-10.00"),
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_debe_y_haber_cero_es_invalido(self, cuenta, tipo_operacion):
        """Un movimiento con ``debe`` y ``haber`` en cero debe lanzar ``ValidationError``."""
        movimiento = MovimientoLibro(
            cuenta=cuenta,
            fecha=FECHA,
            tipo_operacion=tipo_operacion,
            detalle="Movimiento nulo",
            debe=Decimal("0.00"),
            haber=Decimal("0.00"),
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_debe_positivo_es_valido(self, cuenta, tipo_operacion):
        """Un ``debe`` positivo (con ``haber`` cero) debe superar ``full_clean()``."""
        movimiento = MovimientoLibro(
            cuenta=cuenta,
            fecha=FECHA,
            tipo_operacion=tipo_operacion,
            detalle="Depósito válido",
            debe=Decimal("100.00"),
            haber=Decimal("0.00"),
        )
        movimiento.full_clean()  # no debe lanzar ValidationError
