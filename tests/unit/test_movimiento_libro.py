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

from conciliacion.models import (
    ConciliadoBloqueadoError,
    CuentaBancaria,
    MovimientoLibro,
    TipoOperacion,
)

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
        """El primer movimiento suma el ``debe`` al ``saldo_inicial`` de la cuenta."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("250.00"),
        )
        assert movimiento.saldo == Decimal("1250.00")

    @pytest.mark.django_db
    def test_primer_movimiento_resta_haber(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """El primer movimiento resta el ``haber`` del ``saldo_inicial`` de la cuenta."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            haber=Decimal("300.00"),
        )
        assert movimiento.saldo == Decimal("700.00")

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
        assert segundo.saldo == Decimal("1150.00")

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
        assert persistido.saldo == Decimal("1250.00")


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
        assert primero.saldo == Decimal("1100.00")  # 1000 + 100
        assert segundo.saldo == Decimal("1300.00")  # 1100 + 200
        assert tercero.saldo == Decimal("1250.00")  # 1300 - 50

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
            Decimal("1010.00"),
            Decimal("990.00"),
        ]

    @pytest.mark.django_db
    def test_recalcula_en_orden_cronologico_con_inserciones_desordenadas(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Ordena por ``(fecha, id)`` aunque los registros se inserten desordenados."""
        tipo_operacion = tipo_operacion_factory()

        _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 7),
            debe=Decimal("50.00"),
        )
        _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 4),
            haber=Decimal("20.00"),
        )
        _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 5),
            debe=Decimal("30.00"),
        )

        movimientos = MovimientoLibro.recalcular_saldos(cuenta_bancaria.pk)

        # Orden estricto por (fecha, id), no por orden de inserción.
        assert [m.fecha for m in movimientos] == [
            date(2026, 9, 4),
            date(2026, 9, 5),
            date(2026, 9, 7),
        ]
        assert [m.saldo for m in movimientos] == [
            Decimal("980.00"),   # 1000 - 20
            Decimal("1010.00"),  # 980 + 30
            Decimal("1060.00"),  # 1010 + 50
        ]


# ---------------------------------------------------------------------------
# Edición de movimientos y recálculo automático de saldos.
# ---------------------------------------------------------------------------


class TestEdicionMovimientoLibro:
    """Al editar un movimiento, ``recalcular_saldos`` arregla los saldos corridos."""

    @pytest.mark.django_db
    def test_editar_primer_movimiento_recalcula_saldos_posteriores(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Editar el primer movimiento actualiza el saldo de todos los siguientes."""
        tipo_operacion = tipo_operacion_factory()
        primero = _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, haber=Decimal("50.00")
        )
        segundo = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            debe=Decimal("100.00"),
        )

        # Edita el primer movimiento: el haber pasa de 50.00 a 150.00.
        primero.haber = Decimal("150.00")
        primero.save(update_fields=["haber"])

        MovimientoLibro.recalcular_saldos(cuenta_bancaria.pk)

        primero.refresh_from_db()
        segundo.refresh_from_db()
        assert primero.saldo == Decimal("850.00")  # 1000 - 150
        assert segundo.saldo == Decimal("950.00")  # 850 + 100


# ---------------------------------------------------------------------------
# Eliminación de movimientos y recálculo automático de saldos.
# ---------------------------------------------------------------------------


class TestEliminacionMovimientoLibro:
    """Al eliminar un movimiento, ``MovimientoLibro.delete`` recalcula saldos."""

    @pytest.mark.django_db
    def test_eliminar_movimiento_intermedio_recalcula_saldos_posteriores(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Eliminar un movimiento intermedio recalcula los saldos siguientes."""
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

        segundo.delete()

        primero.refresh_from_db()
        tercero.refresh_from_db()
        assert primero.saldo == Decimal("1100.00")  # 1000 + 100
        assert tercero.saldo == Decimal("1050.00")  # 1100 - 50

    @pytest.mark.django_db
    def test_eliminar_ultimo_movimiento_conserva_anteriores(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Eliminar el último movimiento no altera el saldo de los anteriores."""
        tipo_operacion = tipo_operacion_factory()
        primero = _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00")
        )
        _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 7),
            haber=Decimal("40.00"),
        )

        ultimo = MovimientoLibro.objects.filter(cuenta=cuenta_bancaria).order_by(
            "fecha", "id"
        ).last()
        ultimo.delete()

        primero.refresh_from_db()
        assert MovimientoLibro.objects.filter(cuenta=cuenta_bancaria).count() == 1
        assert primero.saldo == Decimal("1100.00")

    @pytest.mark.django_db
    def test_eliminar_primer_movimiento_reinicia_desde_saldo_inicial(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Eliminar el primero recalcula el siguiente desde ``saldo_inicial``."""
        tipo_operacion = tipo_operacion_factory()
        _crear_movimiento_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00")
        )
        segundo = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            debe=Decimal("50.00"),
        )

        primero = MovimientoLibro.objects.filter(cuenta=cuenta_bancaria).order_by(
            "fecha", "id"
        ).first()
        primero.delete()

        segundo.refresh_from_db()
        assert segundo.saldo == Decimal("1050.00")  # 1000 + 50


# ---------------------------------------------------------------------------
# Bloqueo de movimientos conciliados (US4).
# ---------------------------------------------------------------------------


class TestBloqueoEtiquetaConciliado:
    """Un ``MovimientoLibro`` puede quedar marcado como ``conciliado=True``."""

    @pytest.mark.django_db
    def test_crear_movimiento_conciliado_marca_la_etiqueta(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Al crear un movimiento con ``conciliado=True`` el flag queda en ``True``."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("100.00"),
            haber=Decimal("0.00"),
            conciliado=True,
        )
        assert movimiento.conciliado is True


class TestDeleteConciliadoBloqueado:
    """``delete()`` bloquea los movimientos ``conciliado`` y permite el resto."""

    @pytest.mark.django_db
    def test_delete_de_movimiento_conciliado_levanta_error(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Eliminar un movimiento conciliado lanza ``ConciliadoBloqueadoError``."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("100.00"),
            haber=Decimal("0.00"),
            conciliado=True,
        )
        pk = movimiento.pk

        with pytest.raises(ConciliadoBloqueadoError):
            movimiento.delete()

        # La fila sigue existiendo y sus datos no cambiaron.
        assert MovimientoLibro.objects.filter(pk=pk).exists()
        movimiento.refresh_from_db()
        assert movimiento.debe == Decimal("100.00")
        assert movimiento.haber == Decimal("0.00")
        assert movimiento.conciliado is True

    @pytest.mark.django_db
    def test_delete_de_no_conciliado_sigue_funcionando(
        self, cuenta_bancaria, tipo_operacion_factory
    ):
        """Eliminar un movimiento no conciliado no lanza error y borra la fila."""
        movimiento = _crear_movimiento_libro(
            cuenta_bancaria,
            tipo_operacion_factory(),
            debe=Decimal("100.00"),
        )
        pk = movimiento.pk

        movimiento.delete()

        assert not MovimientoLibro.objects.filter(pk=pk).exists()
