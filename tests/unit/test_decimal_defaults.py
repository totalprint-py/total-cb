"""Regression test — money fields must default to Decimal, never float.

Constitution Principle 5 (Money-Decimals invariant): every defaulted money
field on ``CuentaBancaria`` and ``MovimientoLibro`` must be ``Decimal``, never
``float``, even when the row is created WITHOUT passing the amount.

Currently RED because ``CuentaBancaria.saldo_inicial``, ``MovimientoLibro.debe``,
``MovimientoLibro.haber`` y ``MovimientoLibro.saldo`` tienen ``default=0.00``
(literal ``float``) en ``models.py``. Esto provoca ``TypeError`` al crear un
``MovimientoLibro`` con importes ``Decimal`` cuando la cuenta usa el default
de ``saldo_inicial`` (float en memoria antes de leer de BD).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conciliacion.models import CuentaBancaria, MovimientoLibro


FECHA = date(2026, 9, 18)


@pytest.mark.django_db
def test_cuenta_bancaria_saldo_inicial_en_memoria_es_decimal(
    banco_factory, tipo_cuenta_factory, moneda_factory
):
    """Crear una ``CuentaBancaria`` sin pasar ``saldo_inicial`` deja el valor
    en memoria como ``Decimal``, no ``float``.

    El default ``0.00`` (literal float) en ``DecimalField`` hace que la
    instancia en memoria tenga un ``float`` hasta que se lee de BD.
    """
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()

    cuenta = CuentaBancaria.objects.create(
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta de Prueba Decimal",
    )

    # La instancia en memoria (sin releer de BD) debe tener saldo_inicial
    # como Decimal. Si el default es ``0.00`` (float), esto falla.
    assert isinstance(
        cuenta.saldo_inicial, Decimal
    ), f"saldo_inicial en memoria debe ser Decimal, got {type(cuenta.saldo_inicial).__name__}"


@pytest.mark.django_db
def test_movimiento_libro_con_decimal_no_levanta_type_error(
    banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Crear un ``MovimientoLibro`` con ``Decimal`` cuando la cuenta usa el
    default de ``saldo_inicial`` NO debe levantar ``TypeError``.

    Si el bug float/Decimal está vivo, este test falla con::

        TypeError: unsupported operand type(s) for +: 'float' and 'decimal.Decimal'

    en ``models.py:369`` (``saldo_base + self.debe - self.haber``) porque
    ``saldo_base`` proviene de ``cuenta.saldo_inicial`` que es ``float``
    en memoria cuando no se pasó explícitamente, y ``self.debe`` es
    ``Decimal``.
    """
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()

    # Crear cuenta SIN pasar saldo_inicial (usa el default del modelo).
    cuenta = CuentaBancaria.objects.create(
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta de Prueba Decimal",
    )
    # Verificar el estado del bug: saldo_inicial es float en memoria.
    # (No usamos .get() para mantener la instancia en memoria.)

    # Crear movimiento con debe Decimal y haber Decimal.
    # save() ejecutará: float(saldo_inicial) + Decimal(debe) - Decimal(haber)
    # Esto levanta TypeError si el bug está vivo.
    libro = MovimientoLibro(
        cuenta=cuenta,
        fecha=FECHA,
        tipo_operacion=tipo_operacion,
        detalle="Asiento de prueba decimal",
        debe=Decimal("100.00"),
        haber=Decimal("0.00"),
    )
    libro.save()

    libro = MovimientoLibro.objects.get(pk=libro.pk)
    assert isinstance(libro.debe, Decimal), "debe debe ser Decimal, no float"
    assert isinstance(libro.haber, Decimal), "haber debe ser Decimal, no float"
    assert isinstance(libro.saldo, Decimal), "saldo debe ser Decimal, no float"
    assert libro.saldo == Decimal("100.00"), "saldo = 0 + 100 - 0 = 100"


@pytest.mark.django_db
def test_movimiento_libro_defaults_en_memoria_son_decimal(
    banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Los defaults de ``debe``, ``haber`` y ``saldo`` en memoria deben ser
    ``Decimal``, no ``float``.

    Al construir un ``MovimientoLibro`` sin pasar ``debe``/``haber``,
    los valores por defecto del modelo deben ser ``Decimal``.
    """
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()

    cuenta = CuentaBancaria.objects.create(
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta de Prueba Decimal",
    )

    libro = MovimientoLibro(
        cuenta=cuenta,
        fecha=FECHA,
        tipo_operacion=tipo_operacion,
        detalle="Verificar defaults",
    )

    # Los defaults en memoria (antes de save) deben ser Decimal.
    assert isinstance(
        libro.debe, Decimal
    ), f"debe default en memoria debe ser Decimal, got {type(libro.debe).__name__}"
    assert isinstance(
        libro.haber, Decimal
    ), f"haber default en memoria debe ser Decimal, got {type(libro.haber).__name__}"
    assert isinstance(
        libro.saldo, Decimal
    ), f"saldo default en memoria debe ser Decimal, got {type(libro.saldo).__name__}"
