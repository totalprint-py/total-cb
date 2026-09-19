"""Pruebas de las restricciones de base de datos de ``MovimientoLibro`` (FR-007) — RED.

Verifican que ``MovimientoLibro.objects.create()`` con importes negativos o ambos
en cero levante ``IntegrityError`` desde el ``CheckConstraint(condition=Q(...))``
(Principio 1). La creación se envuelve en ``transaction.atomic()`` para capturar
la excepción sin romper la transacción del test.

Estado esperado al escribir estas pruebas: ``MovimientoLibro`` aún no declara
ningún ``CheckConstraint``, por lo que la creación persiste y las pruebas fallan
en rojo (RED).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import transaction
from django.db.utils import IntegrityError

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
    """Devuelve una ``CuentaBancaria`` persistida con ``saldo_inicial`` Decimal."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return _crear_cuenta_bancaria(
        banco, tipo_cuenta, moneda, saldo_inicial=Decimal("0.00")
    )


@pytest.fixture
def tipo_operacion(tipo_operacion_factory):
    """Devuelve un ``TipoOperacion`` persistido."""
    return tipo_operacion_factory()


class TestMovimientoLibroCheckConstraints:
    """Pruebas de las restricciones CHECK de FR-007 a nivel de base de datos."""

    @pytest.mark.django_db
    def test_debe_negativo_viola_check_constraint(self, cuenta, tipo_operacion):
        """Un ``debe`` negativo debe violar el ``CheckConstraint`` (IntegrityError)."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MovimientoLibro.objects.create(
                    cuenta=cuenta,
                    fecha=FECHA,
                    tipo_operacion=tipo_operacion,
                    detalle="Depósito inválido",
                    debe=Decimal("-10.00"),
                    haber=Decimal("0.00"),
                )

    @pytest.mark.django_db
    def test_haber_negativo_viola_check_constraint(self, cuenta, tipo_operacion):
        """Un ``haber`` negativo debe violar el ``CheckConstraint`` (IntegrityError)."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MovimientoLibro.objects.create(
                    cuenta=cuenta,
                    fecha=FECHA,
                    tipo_operacion=tipo_operacion,
                    detalle="Depósito inválido",
                    debe=Decimal("0.00"),
                    haber=Decimal("-10.00"),
                )

    @pytest.mark.django_db
    def test_debe_y_haber_cero_viola_check_constraint(self, cuenta, tipo_operacion):
        """``debe`` y ``haber`` en cero debe violar el ``CheckConstraint`` (IntegrityError)."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MovimientoLibro.objects.create(
                    cuenta=cuenta,
                    fecha=FECHA,
                    tipo_operacion=tipo_operacion,
                    detalle="Movimiento nulo",
                    debe=Decimal("0.00"),
                    haber=Decimal("0.00"),
                )

    @pytest.mark.django_db
    def test_debe_y_haber_positivos_viola_check_constraint(self, cuenta, tipo_operacion):
        """``debe`` y ``haber`` positivos a la vez violan el ``CheckConstraint`` (IntegrityError)."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MovimientoLibro.objects.create(
                    cuenta=cuenta,
                    fecha=FECHA,
                    tipo_operacion=tipo_operacion,
                    detalle="Movimiento ambiguo",
                    debe=Decimal("100.00"),
                    haber=Decimal("50.00"),
                )
