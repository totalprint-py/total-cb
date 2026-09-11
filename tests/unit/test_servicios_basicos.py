"""Pruebas unitarias de las funciones básicas de la capa de servicios (Fase 4 — RED).

Cubre exclusivamente las funciones puras y simples definidas en
``specs/001-core-reconciliation-engine/contracts/service-layer.md``:

* ``assert_decimal``: guarda de tipo que exige ``decimal.Decimal`` y rechaza ``float``.
* ``flag_en_consulta``: bandera "En Consulta" de los movimientos bancarios (FR-013).
* ``set_nota``: notas de texto libre de los movimientos (FR-014).
* ``create_ajuste``: creación de ajustes de conciliación (FR-008).

Estas pruebas se ejecutan contra ``conciliacion/services.py``, que todavía no
existe; por eso deben fallar en rojo (RED) por error de importación. Todas las
descripciones, funciones y variables están en español.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from conciliacion.models import (
    AjusteConciliacion,
    Conciliacion,
    CuentaBancaria,
    LoteImportacion,
    MovimientoBancario,
    MovimientoInterno,
)
from conciliacion.services import (
    EstadoInvalidoError,
    assert_decimal,
    create_ajuste,
    flag_en_consulta,
    set_nota,
)

# ---------------------------------------------------------------------------
# Constantes de apoyo
# ---------------------------------------------------------------------------

FECHA_IMPORTACION = timezone.make_aware(datetime(2026, 9, 5, 10, 30, 0))
FECHA_MOVIMIENTO = date(2026, 9, 5)
FECHA_DESDE = date(2026, 9, 1)
FECHA_HASTA = date(2026, 9, 30)

ESTADOS_NO_BORRADOR = ["committed", "reverted"]


# ---------------------------------------------------------------------------
# Factorías de apoyo (construyen el grafo de datos sin ser objeto de prueba)
# ---------------------------------------------------------------------------


def _crear_lote(**sobrescribir):
    """Crea y persiste un ``LoteImportacion`` de apoyo."""
    valores = {"fuente": "BANCO-X.csv", "fecha_importacion": FECHA_IMPORTACION}
    valores.update(sobrescribir)
    return LoteImportacion.objects.create(**valores)


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


def _crear_movimiento_bancario(cuenta_bancaria, lote_importacion, tipo_operacion, moneda, **sobrescribir):
    """Crea y persiste un ``MovimientoBancario`` de apoyo."""
    valores = {
        "importe": Decimal("100.00"),
        "fecha": FECHA_MOVIMIENTO,
        "cuenta_bancaria": cuenta_bancaria,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoBancario.objects.create(**valores)


def _crear_movimiento_interno(lote_importacion, tipo_operacion, moneda, **sobrescribir):
    """Crea y persiste un ``MovimientoInterno`` de apoyo."""
    valores = {
        "importe": Decimal("80.00"),
        "fecha": FECHA_MOVIMIENTO,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoInterno.objects.create(**valores)


def _crear_conciliacion(cuenta_bancaria, **sobrescribir):
    """Crea y persiste una ``Conciliacion`` de apoyo en estado ``draft``."""
    valores = {
        "estado": Conciliacion.ESTADO_BORRADOR,
        "fecha_desde": FECHA_DESDE,
        "fecha_hasta": FECHA_HASTA,
        "cuenta_bancaria": cuenta_bancaria,
    }
    valores.update(sobrescribir)
    return Conciliacion.objects.create(**valores)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def movimiento_bancario(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Devuelve un ``MovimientoBancario`` persistido con ``en_consulta`` en ``False``."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)
    lote_importacion = _crear_lote()
    return _crear_movimiento_bancario(cuenta_bancaria, lote_importacion, tipo_operacion, moneda)


@pytest.fixture
def movimiento_interno(moneda_factory, tipo_operacion_factory):
    """Devuelve un ``MovimientoInterno`` persistido."""
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    lote_importacion = _crear_lote()
    return _crear_movimiento_interno(lote_importacion, tipo_operacion, moneda)


@pytest.fixture
def conciliacion_borrador(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``Conciliacion`` persistida en estado ``draft`` (borrador)."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)
    return _crear_conciliacion(cuenta_bancaria)

# ---------------------------------------------------------------------------
# ``assert_decimal``
# ---------------------------------------------------------------------------


class TestAssertDecimal:
    """Pruebas de la guarda ``assert_decimal`` (FR-007)."""

    def test_acepta_decimal_y_devuelve_el_mismo_valor(self):
        """Un ``Decimal`` de entrada se devuelve sin alterar su valor."""
        resultado = assert_decimal(Decimal("10.25"))
        assert resultado == Decimal("10.25")

    def test_devuelve_instancia_decimal_desde_decimal(self):
        """El resultado desde un ``Decimal`` es una instancia de ``Decimal``."""
        assert isinstance(assert_decimal(Decimal("10.25")), Decimal)

    def test_acepta_entero_y_devuelve_decimal(self):
        """Un ``int`` de entrada se convierte en ``Decimal`` exacto."""
        resultado = assert_decimal(100)
        assert isinstance(resultado, Decimal)
        assert resultado == Decimal("100")

    def test_acepta_cadena_numerica_y_devuelve_decimal(self):
        """Una cadena numérica se convierte en ``Decimal`` exacto."""
        resultado = assert_decimal("10.25")
        assert isinstance(resultado, Decimal)
        assert resultado == Decimal("10.25")

    def test_preserva_precision_de_la_cadena(self):
        """La precisión expresada en la cadena se conserva sin redondeo binario."""
        assert assert_decimal("0.10") == Decimal("0.10")
        assert assert_decimal("1234567890.12345678") == Decimal("1234567890.12345678")

    def test_valores_negativos_son_aceptados(self):
        """Los valores negativos (int, cadena y Decimal) se aceptan y preservan."""
        assert assert_decimal(-5) == Decimal("-5")
        assert assert_decimal("-10.50") == Decimal("-10.50")
        assert assert_decimal(Decimal("-10.50")) == Decimal("-10.50")

    def test_cero_es_valido(self):
        """El cero se acepta sin alterar la escala explícita de la entrada."""
        assert assert_decimal(0) == Decimal("0")
        assert assert_decimal("0.00") == Decimal("0.00")

    def test_rechaza_float_con_typeerror(self):
        """Un ``float`` se rechaza con ``TypeError`` en la frontera del servicio."""
        with pytest.raises(TypeError):
            assert_decimal(10.25)

    def test_rechaza_float_negativo_con_typeerror(self):
        """Un ``float`` negativo también se rechaza con ``TypeError``."""
        with pytest.raises(TypeError):
            assert_decimal(-0.01)


# ---------------------------------------------------------------------------
# ``flag_en_consulta``
# ---------------------------------------------------------------------------


class TestFlagEnConsulta:
    """Pruebas de ``flag_en_consulta`` (bandera "En Consulta", FR-013)."""

    @pytest.mark.django_db
    def test_activa_la_bandera(self, movimiento_bancario):
        """Activar la bandera persiste ``en_consulta=True``."""
        flag_en_consulta(movimiento_bancario=movimiento_bancario, en_consulta=True)
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.en_consulta is True

    @pytest.mark.django_db
    def test_desactiva_la_bandera(self, movimiento_bancario):
        """Desactivar la bandera persiste ``en_consulta=False``."""
        movimiento_bancario.en_consulta = True
        movimiento_bancario.save()
        flag_en_consulta(movimiento_bancario=movimiento_bancario, en_consulta=False)
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.en_consulta is False

    @pytest.mark.django_db
    def test_devuelve_none(self, movimiento_bancario):
        """La función es de efecto secundario y devuelve ``None``."""
        resultado = flag_en_consulta(movimiento_bancario=movimiento_bancario, en_consulta=True)
        assert resultado is None

    @pytest.mark.django_db
    def test_el_movimiento_permanece_en_la_lista_pendiente(self, movimiento_bancario):
        """Marcar "En Consulta" NO elimina el movimiento de la lista pendiente."""
        flag_en_consulta(movimiento_bancario=movimiento_bancario, en_consulta=True)
        assert MovimientoBancario.objects.filter(pk=movimiento_bancario.pk).exists()
        assert MovimientoBancario.objects.count() == 1

    @pytest.mark.django_db
    def test_no_modifica_importe_fecha_ni_notas(self, movimiento_bancario):
        """La bandera solo cambia ``en_consulta``; no toca importe, fecha ni notas."""
        importe_original = movimiento_bancario.importe
        fecha_original = movimiento_bancario.fecha
        notas_original = movimiento_bancario.notas
        flag_en_consulta(movimiento_bancario=movimiento_bancario, en_consulta=True)
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.importe == importe_original
        assert movimiento_bancario.fecha == fecha_original
        assert movimiento_bancario.notas == notas_original

# ---------------------------------------------------------------------------
# ``set_nota``
# ---------------------------------------------------------------------------


class TestSetNota:
    """Pruebas de ``set_nota`` (notas de texto libre, FR-014)."""

    @pytest.mark.django_db
    def test_establece_nota_en_movimiento_bancario(self, movimiento_bancario):
        """Asigna y persiste la nota en un ``MovimientoBancario``."""
        set_nota(movimiento=movimiento_bancario, texto="Conciliar con ventas")
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.notas == "Conciliar con ventas"

    @pytest.mark.django_db
    def test_establece_nota_en_movimiento_interno(self, movimiento_interno):
        """Asigna y persiste la nota en un ``MovimientoInterno``."""
        set_nota(movimiento=movimiento_interno, texto="Post-it interno")
        movimiento_interno.refresh_from_db()
        assert movimiento_interno.notas == "Post-it interno"

    @pytest.mark.django_db
    def test_devuelve_none(self, movimiento_bancario):
        """La función es de efecto secundario y devuelve ``None``."""
        assert set_nota(movimiento=movimiento_bancario, texto="Nota") is None

    @pytest.mark.django_db
    def test_no_modifica_importe_fecha_ni_bandera(self, movimiento_bancario):
        """La nota no altera importe, fecha ni la bandera ``en_consulta``."""
        importe_original = movimiento_bancario.importe
        fecha_original = movimiento_bancario.fecha
        bandera_original = movimiento_bancario.en_consulta
        set_nota(movimiento=movimiento_bancario, texto="Nota de prueba")
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.importe == importe_original
        assert movimiento_bancario.fecha == fecha_original
        assert movimiento_bancario.en_consulta == bandera_original

    @pytest.mark.django_db
    def test_no_modifica_importe_ni_fecha_del_interno(self, movimiento_interno):
        """La nota en un ``MovimientoInterno`` no altera importe ni fecha."""
        importe_original = movimiento_interno.importe
        fecha_original = movimiento_interno.fecha
        set_nota(movimiento=movimiento_interno, texto="Nota")
        movimiento_interno.refresh_from_db()
        assert movimiento_interno.importe == importe_original
        assert movimiento_interno.fecha == fecha_original

    @pytest.mark.django_db
    def test_nota_vacia_se_persiste(self, movimiento_bancario):
        """Una nota vacía (``""``) es un valor válido y se persiste."""
        set_nota(movimiento=movimiento_bancario, texto="")
        movimiento_bancario.refresh_from_db()
        assert movimiento_bancario.notas == ""

# ---------------------------------------------------------------------------
# ``create_ajuste``
# ---------------------------------------------------------------------------


class TestCreateAjuste:
    """Pruebas de ``create_ajuste`` (creación de ajustes de conciliación, FR-008)."""

    @pytest.mark.django_db
    def test_persiste_ajuste_con_importe_decimal(self, conciliacion_borrador, concepto_ajuste_factory):
        """Un importe ``Decimal`` se persiste con sus claves foráneas."""
        concepto = concepto_ajuste_factory()
        ajuste = create_ajuste(
            conciliacion=conciliacion_borrador,
            concepto_ajuste=concepto,
            importe=Decimal("25.00"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("25.00")
        assert persistido.conciliacion_id == conciliacion_borrador.pk
        assert persistido.concepto_ajuste_id == concepto.pk

    @pytest.mark.django_db
    def test_devuelve_instancia_de_ajuste_conciliacion(self, conciliacion_borrador, concepto_ajuste_factory):
        """Devuelve una instancia persistida de ``AjusteConciliacion``."""
        ajuste = create_ajuste(
            conciliacion=conciliacion_borrador,
            concepto_ajuste=concepto_ajuste_factory(),
            importe=Decimal("25.00"),
        )
        assert isinstance(ajuste, AjusteConciliacion)
        assert ajuste.pk is not None

    @pytest.mark.django_db
    def test_ajuste_negativo_se_persiste(self, conciliacion_borrador, concepto_ajuste_factory):
        """Un ajuste negativo (que compensa diferencias) se persiste exactamente."""
        ajuste = create_ajuste(
            conciliacion=conciliacion_borrador,
            concepto_ajuste=concepto_ajuste_factory(),
            importe=Decimal("-25.00"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("-25.00")

    @pytest.mark.django_db
    def test_ajuste_cero_se_persiste(self, conciliacion_borrador, concepto_ajuste_factory):
        """Un ajuste de importe cero es válido y no rompe la suma cero."""
        ajuste = create_ajuste(
            conciliacion=conciliacion_borrador,
            concepto_ajuste=concepto_ajuste_factory(),
            importe=Decimal("0.00"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("0.00")

    @pytest.mark.django_db
    def test_rechaza_importe_float_con_typeerror(self, conciliacion_borrador, concepto_ajuste_factory):
        """Un importe ``float`` se rechaza con ``TypeError`` (vía ``assert_decimal``)."""
        with pytest.raises(TypeError):
            create_ajuste(
                conciliacion=conciliacion_borrador,
                concepto_ajuste=concepto_ajuste_factory(),
                importe=1500.75,
            )

    @pytest.mark.django_db
    @pytest.mark.parametrize("estado_no_borrador", ESTADOS_NO_BORRADOR)
    def test_rechaza_conciliacion_no_borrador(self, conciliacion_borrador, concepto_ajuste_factory, estado_no_borrador):
        """Una ``Conciliacion`` que no está en ``draft`` se rechaza con ``EstadoInvalidoError``."""
        conciliacion_borrador.estado = estado_no_borrador
        conciliacion_borrador.save()
        with pytest.raises(EstadoInvalidoError):
            create_ajuste(
                conciliacion=conciliacion_borrador,
                concepto_ajuste=concepto_ajuste_factory(),
                importe=Decimal("25.00"),
            )




