"""Pruebas unitarias de la agregación de reportes del Libro Bancario (Fase 2 — RED).

Cubren ``conciliacion/reportes.py``, fuente única de la proyección de solo
lectura consumida por los cuatro formatos de salida (FR-007/FR-009):

* ``generar_reporte_libro()`` filtra por cuenta + rango inclusivo y ordena por
  ``fecha`` e ``id`` (FR-002);
* saldo inicial del periodo = ``saldo`` del último movimiento con
  ``fecha < desde``, o ``saldo_inicial`` de la cuenta si no existe (FR-004);
* totales ``total_debe``/``total_haber`` y ``saldo_final = saldo_inicial_periodo
  + total_debe - total_haber`` (FR-005);
* rango vacío → totales en ``Decimal("0.00")`` y ``saldo_final`` igual al saldo
  inicial del periodo;
* ``fecha_desde > fecha_hasta`` → ``RangoFechasInvalidoError`` (FR-008);
* aritmética exclusivamente con ``decimal.Decimal``, nunca ``float`` (FR-010);
* la llamada es estrictamente de solo lectura (FR-009).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conciliacion.models import CuentaBancaria, MovimientoLibro
from conciliacion.reportes import (
    RangoFechasInvalidoError,
    ReporteLibro,
    generar_reporte_libro,
)


# ---------------------------------------------------------------------------
# Fábricas de apoyo (persisten el grafo de datos sin ser objeto de prueba).
# ---------------------------------------------------------------------------


def _crear_cuenta(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` de apoyo con saldo inicial 1000.00."""
    valores = {
        "numero_cuenta": "0001-2345-6789",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
        "saldo_inicial": Decimal("1000.00"),
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


def _crear_movimiento(cuenta, tipo_operacion, fecha, **sobrescribir):
    """Crea y persiste un ``MovimientoLibro`` de apoyo."""
    valores = {
        "cuenta": cuenta,
        "fecha": fecha,
        "tipo_operacion": tipo_operacion,
        "detalle": "Movimiento de prueba",
        "debe": Decimal("0.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


@pytest.fixture
def cuenta(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida con ``saldo_inicial=1000.00``."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return _crear_cuenta(banco, tipo_cuenta, moneda)


@pytest.fixture
def escenario(cuenta, tipo_operacion_factory):
    """Cuenta con saldo inicial 1000.00 y cuatro movimientos cronológicos.

    Cronología (saldo corrido calculado por el motor ``save()``):

    * 2026-01-05  debe 100.00  → saldo 1100.00
    * 2026-01-10  haber 50.00  → saldo 1050.00
    * 2026-02-02  debe 200.00  → saldo 1250.00
    * 2026-03-01  haber 300.00 → saldo 950.00
    """
    tipo = tipo_operacion_factory()
    movimientos = [
        _crear_movimiento(cuenta, tipo, date(2026, 1, 5), debe=Decimal("100.00")),
        _crear_movimiento(cuenta, tipo, date(2026, 1, 10), haber=Decimal("50.00")),
        _crear_movimiento(cuenta, tipo, date(2026, 2, 2), debe=Decimal("200.00")),
        _crear_movimiento(cuenta, tipo, date(2026, 3, 1), haber=Decimal("300.00")),
    ]
    return {"cuenta": cuenta, "movimientos": movimientos}


# ---------------------------------------------------------------------------
# Filtrado y orden (FR-002)
# ---------------------------------------------------------------------------


class TestFiltradoYOrden:
    """Pruebas del filtro por cuenta + rango inclusivo y el orden fecha/id."""

    @pytest.mark.django_db
    def test_filtra_solo_movimientos_del_rango(self, escenario):
        """Solo se listan los movimientos con ``desde <= fecha <= hasta``."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 1, 31),
        )
        assert [m.fecha for m in resultado.movimientos] == [
            date(2026, 1, 5),
            date(2026, 1, 10),
        ]

    @pytest.mark.django_db
    def test_limites_son_inclusivos(self, escenario):
        """Las fechas ``desde`` y ``hasta`` incluyen los movimientos de sus bordes."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 1, 10),
        )
        assert [m.fecha for m in resultado.movimientos] == [
            date(2026, 1, 5),
            date(2026, 1, 10),
        ]

    @pytest.mark.django_db
    def test_no_mezcla_movimientos_de_otras_cuentas(
        self, cuenta, banco_factory, tipo_cuenta_factory, moneda_factory,
        tipo_operacion_factory,
    ):
        """La agregación no incluye renglones de otra cuenta bancaria."""
        banco2 = banco_factory(codigo="BCO-002", nombre="Otro Banco")
        tipo_cuenta2 = tipo_cuenta_factory(codigo="CTA-002", nombre="Caja de Ahorro")
        moneda2 = moneda_factory(codigo="EUR", nombre="Euro")
        otra_cuenta = _crear_cuenta(banco2, tipo_cuenta2, moneda2)
        tipo = tipo_operacion_factory()
        _crear_movimiento(
            otra_cuenta, tipo, date(2026, 2, 5), debe=Decimal("999.00")
        )

        resultado = generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 12, 31),
        )

        assert all(m.cuenta_id == cuenta.pk for m in resultado.movimientos)
        assert resultado.total_debe == Decimal("0.00")

    @pytest.mark.django_db
    def test_ordena_por_fecha_y_luego_id(self, cuenta, tipo_operacion_factory):
        """Aun insertando fuera de orden, el reporte ordena por fecha e id."""
        tipo = tipo_operacion_factory()
        # Se insertan intencionalmente fuera de orden cronológico; el saldo se
        # repara después con el reparador oficial del motor.
        _crear_movimiento(cuenta, tipo, date(2026, 5, 1), debe=Decimal("10.00"))
        _crear_movimiento(cuenta, tipo, date(2026, 4, 1), haber=Decimal("5.00"))
        MovimientoLibro.recalcular_saldos(cuenta.pk)

        resultado = generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=date(2026, 4, 1),
            fecha_hasta=date(2026, 5, 1),
        )

        assert [m.fecha for m in resultado.movimientos] == [
            date(2026, 4, 1),
            date(2026, 5, 1),
        ]

    @pytest.mark.django_db
    def test_empate_de_fecha_se_desempata_por_id(self, cuenta, tipo_operacion_factory):
        """Dos movimientos con la misma fecha conservan el orden de id."""
        tipo = tipo_operacion_factory()
        primero = _crear_movimiento(cuenta, tipo, date(2026, 2, 2), debe=Decimal("10.00"))
        segundo = _crear_movimiento(cuenta, tipo, date(2026, 2, 2), haber=Decimal("5.00"))

        resultado = generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=date(2026, 2, 2),
            fecha_hasta=date(2026, 2, 2),
        )

        assert [m.pk for m in resultado.movimientos] == [primero.pk, segundo.pk]


# ---------------------------------------------------------------------------
# Saldo inicial del periodo (FR-004)
# ---------------------------------------------------------------------------


class TestSaldoInicialPeriodo:
    """Pruebas del saldo de apertura del rango seleccionado."""

    @pytest.mark.django_db
    def test_sin_movimientos_previos_usa_saldo_inicial_de_la_cuenta(self, escenario):
        """Sin renglones anteriores al rango, el saldo inicial es el de la cuenta."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 4),
        )
        assert resultado.saldo_inicial_periodo == Decimal("1000.00")

    @pytest.mark.django_db
    def test_usa_saldo_del_ultimo_movimiento_anterior_al_rango(self, escenario):
        """El saldo inicial del periodo es el saldo del último renglón anterior."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 2, 2),
            fecha_hasta=date(2026, 2, 28),
        )
        # Último movimiento con fecha < 2026-02-02: el haber de 50.00 (saldo 1050.00).
        assert resultado.saldo_inicial_periodo == Decimal("1050.00")


# ---------------------------------------------------------------------------
# Totales y saldo final (FR-005)
# ---------------------------------------------------------------------------


class TestTotalesYSaldoFinal:
    """Pruebas de los totales del pie y del saldo final."""

    @pytest.mark.django_db
    def test_totales_y_saldo_final_coinciden_con_el_motor(self, escenario):
        """``saldo_final = saldo_inicial_periodo + total_debe - total_haber``."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 3, 1),
        )
        assert resultado.saldo_inicial_periodo == Decimal("1000.00")
        assert resultado.total_debe == Decimal("300.00")
        assert resultado.total_haber == Decimal("350.00")
        assert resultado.saldo_final == Decimal("950.00")
        # El saldo final coincide con el saldo corrido del último renglón.
        assert resultado.saldo_final == resultado.movimientos[-1].saldo


# ---------------------------------------------------------------------------
# Rango vacío (FR-005)
# ---------------------------------------------------------------------------


class TestRangoVacio:
    """Pruebas de un rango sin movimientos."""

    @pytest.mark.django_db
    def test_rango_vacio_totales_cero_y_saldo_final_igual_al_inicial(self, escenario):
        """Un rango sin renglones devuelve totales cero y saldo final de apertura."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 4, 1),
            fecha_hasta=date(2026, 4, 30),
        )
        assert resultado.movimientos == []
        assert resultado.total_debe == Decimal("0.00")
        assert resultado.total_haber == Decimal("0.00")
        # Apertura = saldo del último movimiento anterior (2026-03-01 → 950.00).
        assert resultado.saldo_inicial_periodo == Decimal("950.00")
        assert resultado.saldo_final == Decimal("950.00")

    @pytest.mark.django_db
    def test_rango_vacio_al_inicio_sin_movimientos_previos(self, escenario):
        """Rango vacío situado antes de cualquier movimiento."""
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2025, 12, 1),
            fecha_hasta=date(2025, 12, 31),
        )
        assert resultado.movimientos == []
        assert resultado.saldo_inicial_periodo == Decimal("1000.00")
        assert resultado.saldo_final == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Rango inválido (FR-008)
# ---------------------------------------------------------------------------


class TestRangoInvalido:
    """Pruebas de validación del rango de fechas."""

    @pytest.mark.django_db
    def test_desde_posterior_a_hasta_lanza_error(self, escenario):
        """``fecha_desde > fecha_hasta`` lanza ``RangoFechasInvalidoError``."""
        with pytest.raises(RangoFechasInvalidoError):
            generar_reporte_libro(
                cuenta=escenario["cuenta"],
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 1, 1),
            )

    @pytest.mark.django_db
    def test_fechas_que_no_son_date_lanzan_error(self, escenario):
        """Un valor que no es ``date`` se rechaza con el error de dominio."""
        with pytest.raises(RangoFechasInvalidoError):
            generar_reporte_libro(
                cuenta=escenario["cuenta"],
                fecha_desde="2026-01-01",
                fecha_hasta=date(2026, 1, 31),
            )


# ---------------------------------------------------------------------------
# Precisión monetaria (FR-010)
# ---------------------------------------------------------------------------


class TestPrecisionDecimal:
    """Pruebas de que todo valor monetario del reporte es ``Decimal``."""

    @pytest.mark.django_db
    def test_valores_monetarios_son_decimal_y_nunca_float(self, escenario):
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 3, 1),
        )
        for valor in (
            resultado.saldo_inicial_periodo,
            resultado.total_debe,
            resultado.total_haber,
            resultado.saldo_final,
        ):
            assert isinstance(valor, Decimal)
            assert not isinstance(valor, float)


# ---------------------------------------------------------------------------
# Solo lectura (FR-009)
# ---------------------------------------------------------------------------


class TestSoloLectura:
    """Pruebas de que generar un reporte no muta los datos."""

    @pytest.mark.django_db
    def test_no_crea_ni_modifica_registros(self, escenario):
        cuenta = escenario["cuenta"]
        movimientos_antes = MovimientoLibro.objects.count()
        cuentas_antes = CuentaBancaria.objects.count()

        generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 12, 31),
        )

        assert MovimientoLibro.objects.count() == movimientos_antes
        assert CuentaBancaria.objects.count() == cuentas_antes


# ---------------------------------------------------------------------------
# Tipo de resultado ``ReporteLibro``
# ---------------------------------------------------------------------------


class TestReporteLibro:
    """Pruebas del tipo de resultado congelado."""

    @pytest.mark.django_db
    def test_devuelve_instancia_reportelibro_con_campos_esperados(self, escenario):
        cuenta = escenario["cuenta"]
        resultado = generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 1, 10),
        )
        assert isinstance(resultado, ReporteLibro)
        assert resultado.cuenta.pk == cuenta.pk
        assert resultado.fecha_desde == date(2026, 1, 5)
        assert resultado.fecha_hasta == date(2026, 1, 10)
        assert isinstance(resultado.movimientos, list)

    @pytest.mark.django_db
    def test_es_inmutable(self, escenario):
        resultado = generar_reporte_libro(
            cuenta=escenario["cuenta"],
            fecha_desde=date(2026, 1, 5),
            fecha_hasta=date(2026, 1, 10),
        )
        with pytest.raises(AttributeError):
            resultado.total_debe = Decimal("999.00")
