"""Pruebas unitarias de ``MovimientoLibro`` (libro mayor con saldo corrido).

Verifican:

* el esquema de campos (``fecha``, ``detalle``, ``debe``/``haber``/``saldo``
  decimales 18,2, ``conciliado`` y sus relaciones);
* el motor de saldo en ``save()``: el primer movimiento parte del
  ``saldo_inicial`` de la cuenta y los siguientes del movimiento anterior;
* el reparador ``recalcular_saldos`` que reconstruye saldos corruptos en
  orden cronológico.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import models

from conciliacion.models import CuentaBancaria, MovimientoLibro, TipoOperacion

FECHA = date(2026, 9, 5)


# ---------------------------------------------------------------------------
# Fábricas de apoyo (persisten el grafo de datos sin ser objeto de prueba).
# ---------------------------------------------------------------------------


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


def _crear_movimiento_libro(cuenta, tipo_operacion, **sobrescribir):
    """Crea y persiste un ``MovimientoLibro`` de apoyo."""
    valores = {
        "cuenta": cuenta,
        "fecha": FECHA,
        "tipo_operacion": tipo_operacion,
        "detalle": "Movimiento de prueba",
        "debe": Decimal("0.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


@pytest.fixture
def cuenta_bancaria(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida con ``saldo_inicial=1000.00``."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return _crear_cuenta_bancaria(
        banco, tipo_cuenta, moneda, saldo_inicial=Decimal("1000.00")
    )


# ---------------------------------------------------------------------------
# Esquema de campos
# ---------------------------------------------------------------------------


class TestMovimientoLibroEsquema:
    """Pruebas del esquema de campos de ``MovimientoLibro``."""

    def test_fecha_es_datefield(self):
        """El campo ``fecha`` debe ser un ``DateField``."""
        campo = MovimientoLibro._meta.get_field("fecha")
        assert isinstance(campo, models.DateField)

    def test_detalle_es_charfield_de_255(self):
        """El campo ``detalle`` debe ser un ``CharField`` con ``max_length=255``."""
        campo = MovimientoLibro._meta.get_field("detalle")
        assert isinstance(campo, models.CharField)
        assert campo.max_length == 255

    def test_debe_haber_y_saldo_son_decimalfields_18_2(self):
        """``debe``, ``haber`` y ``saldo`` deben ser ``DecimalField`` con precisión 18,2."""
        for nombre in ("debe", "haber", "saldo"):
            campo = MovimientoLibro._meta.get_field(nombre)
            assert isinstance(campo, models.DecimalField)
            assert campo.max_digits == 18
            assert campo.decimal_places == 2

    def test_conciliado_es_booleano_con_default_false(self):
        """El campo ``conciliado`` debe ser ``BooleanField`` con valor por defecto ``False``."""
        campo = MovimientoLibro._meta.get_field("conciliado")
        assert isinstance(campo, models.BooleanField)
        assert campo.default is False

    def test_saldo_es_no_editable(self):
        """El campo ``saldo`` debe ser de solo lectura (``editable=False``)."""
        campo = MovimientoLibro._meta.get_field("saldo")
        assert campo.editable is False

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino, on_delete",
        [
            ("cuenta", CuentaBancaria, models.CASCADE),
            ("tipo_operacion", TipoOperacion, models.PROTECT),
        ],
        ids=["cuenta", "tipo_operacion"],
    )
    def test_relaciones(self, nombre_campo, modelo_destino, on_delete):
        """Cada relación debe ser una ``ForeignKey`` hacia el modelo y ``on_delete`` correctos."""
        campo = MovimientoLibro._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.remote_field.on_delete is on_delete

    def test_ordering_es_fecha_id(self):
        """El orden por defecto debe ser ``['fecha', 'id']``."""
        assert MovimientoLibro._meta.ordering == ["fecha", "id"]


# ---------------------------------------------------------------------------
# Motor de saldo corrido en ``save()``
# ---------------------------------------------------------------------------


class TestMotorSaldoMovimientoLibro:
    """Pruebas del cálculo automático del saldo en ``save()``."""

    @pytest.mark.django_db
    def test_primer_movimiento_calcula_saldo_desde_saldo_inicial(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """El primer movimiento resta el ``debe`` del ``saldo_inicial`` de la cuenta."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("250.00"),
        )
        assert movimiento.saldo == Decimal("750.00")

    @pytest.mark.django_db
    def test_primer_movimiento_suma_haber(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """El primer movimiento suma el ``haber`` al ``saldo_inicial`` de la cuenta."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            haber=Decimal("300.00"),
        )
        assert movimiento.saldo == Decimal("1300.00")

    @pytest.mark.django_db
    def test_movimiento_siguiente_calcula_saldo_desde_anterior(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Un movimiento posterior parte del saldo del movimiento anterior."""
        tipo_operacion = tipo_operacion_factory()
        _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("250.00")
        )
        segundo = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            haber=Decimal("100.00"),
        )
        assert segundo.saldo == Decimal("850.00")

    @pytest.mark.django_db
    def test_saldo_calculado_se_persiste(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """El saldo calculado debe persistirse en la base de datos."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("250.00"),
        )
        persistido = MovimientoLibro.objects.get(pk=movimiento.pk)
        assert persistido.saldo == Decimal("750.00")


# ---------------------------------------------------------------------------
# ``recalcular_saldos``
# ---------------------------------------------------------------------------


class TestRecalcularSaldos:
    """Pruebas del reparador de saldos corridos ``recalcular_saldos``."""

    @pytest.mark.django_db
    def test_corrige_saldos_corruptos(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Reconstruye el saldo de cada movimiento en orden cronológico."""
        tipo_operacion = tipo_operacion_factory()
        primero = _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00")
        )
        segundo = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            debe=Decimal("200.00"),
        )
        tercero = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 7),
            haber=Decimal("50.00"),
        )

        # Corrompe los saldos saltándose el motor de ``save()``.
        MovimientoLibro.objects.filter(
            pk__in=[primero.pk, segundo.pk, tercero.pk]
        ).update(saldo=Decimal("9999.99"))

        MovimientoLibro.recalcular_saldos(cuenta_bancaria.pk)

        primero.refresh_from_db()
        segundo.refresh_from_db()
        tercero.refresh_from_db()
        assert primero.saldo == Decimal("900.00")  # 1000 - 100
        assert segundo.saldo == Decimal("700.00")  # 900 - 200
        assert tercero.saldo == Decimal("750.00")  # 700 + 50

    @pytest.mark.django_db
    def test_devuelve_movimientos_actualizados(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Devuelve la lista de movimientos recorridos."""
        tipo_operacion = tipo_operacion_factory()
        _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("10.00")
        )
        _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            haber=Decimal("20.00"),
        )
        movimientos = MovimientoLibro.recalcular_saldos(cuenta_bancaria.pk)
        assert len(movimientos) == 2
        assert [m.saldo for m in movimientos] == [
            Decimal("990.00"),
            Decimal("1010.00"),
        ]
