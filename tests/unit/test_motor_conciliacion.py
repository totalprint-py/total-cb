"""Pruebas unitarias para las entidades del motor de conciliación.

Este módulo cubre exclusivamente las entidades de conciliación definidas en
``specs/001-core-reconciliation-engine/data-model.md``:

* ``Conciliacion``
* ``DetalleConciliacionBancaria``
* ``DetalleConciliacionInterna``
* ``AjusteConciliacion``

Las pruebas verifican tanto la estructura (tipos de campo, claves foráneas,
restricciones declaradas en ``Meta.constraints``) como el comportamiento de
validación y de persistencia:

* ``Conciliacion.estado`` debe ser ``draft``, ``committed`` o ``reverted``
  (transición de estados del motor) y está protegido por un ``CheckConstraint``
  con nombre explícito, sin ``check=`` obsoleto.
* Cada detalle (bancario o interno) vincula un único movimiento a una única
  conciliación mediante ``UniqueConstraint`` (par único).
* ``AjusteConciliacion.importe`` es un ``DecimalField`` (nunca ``FloatField``);
  asignar un ``float`` debe fallar (validación o error de tipo), forzando el
  uso de ``decimal.Decimal``.

Todas las descripciones, funciones y variables están en español.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models.constraints import CheckConstraint, UniqueConstraint
from django.utils import timezone

from conciliacion.models import (
    AjusteConciliacion,
    ConceptoAjuste,
    Conciliacion,
    CuentaBancaria,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
    LoteImportacion,
    MovimientoBancario,
    MovimientoInterno,
)

# ---------------------------------------------------------------------------
# Constantes de apoyo
# ---------------------------------------------------------------------------

FECHA_IMPORTACION = timezone.make_aware(datetime(2026, 9, 5, 10, 30, 0))
FECHA_MOVIMIENTO = date(2026, 9, 5)
FECHA_DESDE = date(2026, 9, 1)
FECHA_HASTA = date(2026, 9, 30)

ESTADOS_VALIDOS = {"draft", "committed", "reverted"}


# ---------------------------------------------------------------------------
# Factorías de apoyo (construyen el grafo de datos sin ser objeto de prueba)
# ---------------------------------------------------------------------------

def _crear_lote(**sobrescribir):
    """Crea un ``LoteImportacion`` de apoyo para vincular movimientos."""
    valores = {
        "fuente": "Banco Prueba",
        "fecha_importacion": FECHA_IMPORTACION,
    }
    valores.update(sobrescribir)
    return LoteImportacion.objects.create(**valores)


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea una ``CuentaBancaria`` de apoyo."""
    valores = {
        "numero_cuenta": "0001-0002-0003",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


def _crear_movimiento_bancario(cuenta_bancaria, lote_importacion, tipo_operacion, moneda, **sobrescribir):
    """Crea un ``MovimientoBancario`` de apoyo."""
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
    """Crea un ``MovimientoInterno`` de apoyo."""
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
    """Crea una ``Conciliacion`` de apoyo en estado ``draft``."""
    valores = {
        "estado": "draft",
        "fecha_desde": FECHA_DESDE,
        "fecha_hasta": FECHA_HASTA,
        "cuenta_bancaria": cuenta_bancaria,
    }
    valores.update(sobrescribir)
    return Conciliacion.objects.create(**valores)


def _crear_detalle_bancaria(conciliacion, movimiento_bancario, **sobrescribir):
    """Crea un ``DetalleConciliacionBancaria`` de apoyo."""
    valores = {
        "conciliacion": conciliacion,
        "movimiento_bancario": movimiento_bancario,
    }
    valores.update(sobrescribir)
    return DetalleConciliacionBancaria.objects.create(**valores)


def _crear_detalle_interna(conciliacion, movimiento_interno, **sobrescribir):
    """Crea un ``DetalleConciliacionInterna`` de apoyo."""
    valores = {
        "conciliacion": conciliacion,
        "movimiento_interno": movimiento_interno,
    }
    valores.update(sobrescribir)
    return DetalleConciliacionInterna.objects.create(**valores)


def _crear_ajuste(conciliacion, concepto_ajuste, **sobrescribir):
    """Crea un ``AjusteConciliacion`` de apoyo."""
    valores = {
        "importe": Decimal("10.00"),
        "conciliacion": conciliacion,
        "concepto_ajuste": concepto_ajuste,
    }
    valores.update(sobrescribir)
    return AjusteConciliacion.objects.create(**valores)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def grafo_conciliacion(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Construye el grafo completo: cuenta, conciliación y movimientos (bancario e interno)."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)
    lote_importacion = _crear_lote()
    conciliacion = _crear_conciliacion(cuenta_bancaria)
    movimiento_bancario = _crear_movimiento_bancario(
        cuenta_bancaria, lote_importacion, tipo_operacion, moneda
    )
    movimiento_interno = _crear_movimiento_interno(lote_importacion, tipo_operacion, moneda)
    return {
        "conciliacion": conciliacion,
        "cuenta_bancaria": cuenta_bancaria,
        "movimiento_bancario": movimiento_bancario,
        "movimiento_interno": movimiento_interno,
    }


# ---------------------------------------------------------------------------
# ``Conciliacion``
# ---------------------------------------------------------------------------


class TestConciliacion:
    """Pruebas de estructura y comportamiento para ``Conciliacion``."""

    def test_estado_es_charfield(self):
        """El campo ``estado`` es una cadena de texto (``CharField``)."""
        campo = Conciliacion._meta.get_field("estado")
        assert isinstance(campo, models.CharField)

    def test_estado_es_obligatorio(self):
        """El campo ``estado`` no admite ``NULL`` ni valores vacíos."""
        campo = Conciliacion._meta.get_field("estado")
        assert campo.null is False
        assert campo.blank is False

    def test_estado_tiene_opciones_validas(self):
        """El campo ``estado`` sólo admite ``draft``, ``committed`` y ``reverted``."""
        campo = Conciliacion._meta.get_field("estado")
        valores = {opcion[0] for opcion in campo.choices}
        assert valores == ESTADOS_VALIDOS

    def test_estado_por_defecto_es_borrador(self):
        """Una ``Conciliacion`` nueva comienza en estado ``draft`` (borrador)."""
        assert Conciliacion().estado == "draft"

    def test_estado_tiene_restriccion_de_valores_validos(self):
        """El estado válido está protegido por un ``CheckConstraint`` con nombre explícito."""
        restricciones = {restriccion.name: restriccion for restriccion in Conciliacion._meta.constraints}
        assert "conciliacion_estado_valido" in restricciones
        restriccion = restricciones["conciliacion_estado_valido"]
        assert isinstance(restriccion, CheckConstraint)
        # ``condition`` (no el obsoleto ``check=``) restringe ``estado`` a los valores válidos.
        valores_por_lookup = {lookup: valor for lookup, valor in restriccion.condition.children}
        assert "estado__in" in valores_por_lookup
        assert set(valores_por_lookup["estado__in"]) == ESTADOS_VALIDOS

    def test_fecha_desde_es_datefield(self):
        """El campo ``fecha_desde`` es una fecha (``DateField``)."""
        campo = Conciliacion._meta.get_field("fecha_desde")
        assert isinstance(campo, models.DateField)

    def test_fecha_desde_es_obligatorio(self):
        """El campo ``fecha_desde`` no admite ``NULL`` ni valores vacíos."""
        campo = Conciliacion._meta.get_field("fecha_desde")
        assert campo.null is False
        assert campo.blank is False

    def test_fecha_hasta_es_datefield(self):
        """El campo ``fecha_hasta`` es una fecha (``DateField``)."""
        campo = Conciliacion._meta.get_field("fecha_hasta")
        assert isinstance(campo, models.DateField)

    def test_fecha_hasta_es_obligatorio(self):
        """El campo ``fecha_hasta`` no admite ``NULL`` ni valores vacíos."""
        campo = Conciliacion._meta.get_field("fecha_hasta")
        assert campo.null is False
        assert campo.blank is False

    def test_relacion_con_cuenta_bancaria_es_obligatoria(self):
        """``Conciliacion`` debe apuntar a una ``CuentaBancaria`` obligatoria."""
        campo = Conciliacion._meta.get_field("cuenta_bancaria")
        assert campo.many_to_one is True
        assert campo.remote_field.model is CuentaBancaria
        assert campo.null is False

    @pytest.mark.django_db
    def test_estado_invalido_falla_la_validacion(self, grafo_conciliacion):
        """Un ``estado`` no contemplado no supera la validación del modelo."""
        conciliacion = Conciliacion(
            estado="inexistente",
            fecha_desde=FECHA_DESDE,
            fecha_hasta=FECHA_HASTA,
            cuenta_bancaria=grafo_conciliacion["cuenta_bancaria"],
        )
        with pytest.raises(ValidationError):
            conciliacion.full_clean()

    @pytest.mark.django_db
    def test_estado_invalido_es_rechazado_por_la_base_de_datos(self, grafo_conciliacion):
        """Un ``estado`` no contemplado es rechazado por la base de datos (``IntegrityError``)."""
        with pytest.raises(IntegrityError):
            _crear_conciliacion(
                grafo_conciliacion["cuenta_bancaria"],
                estado="inexistente",
            )

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self, grafo_conciliacion):
        """Crear una ``Conciliacion`` persiste estado, fechas y la cuenta asociada."""
        conciliacion = grafo_conciliacion["conciliacion"]
        persistida = Conciliacion.objects.get(pk=conciliacion.pk)
        assert persistida.estado == "draft"
        assert persistida.fecha_desde == FECHA_DESDE
        assert persistida.fecha_hasta == FECHA_HASTA
        assert persistida.cuenta_bancaria_id == grafo_conciliacion["cuenta_bancaria"].pk


# ---------------------------------------------------------------------------
# ``DetalleConciliacionBancaria``
# ---------------------------------------------------------------------------


class TestDetalleConciliacionBancaria:
    """Pruebas de estructura y comportamiento para ``DetalleConciliacionBancaria``."""

    def test_relacion_con_conciliacion_es_obligatoria(self):
        """``DetalleConciliacionBancaria`` debe apuntar a una ``Conciliacion`` obligatoria."""
        campo = DetalleConciliacionBancaria._meta.get_field("conciliacion")
        assert campo.many_to_one is True
        assert campo.remote_field.model is Conciliacion
        assert campo.null is False

    def test_relacion_con_movimiento_bancario_es_obligatoria(self):
        """``DetalleConciliacionBancaria`` debe apuntar a un ``MovimientoBancario`` obligatorio."""
        campo = DetalleConciliacionBancaria._meta.get_field("movimiento_bancario")
        assert campo.many_to_one is True
        assert campo.remote_field.model is MovimientoBancario
        assert campo.null is False

    def test_par_conciliacion_movimiento_es_unico(self):
        """El par ``(conciliacion, movimiento_bancario)`` es único (``UniqueConstraint``)."""
        restricciones = {
            restriccion.name: restriccion for restriccion in DetalleConciliacionBancaria._meta.constraints
        }
        assert "detalle_conciliacion_bancaria_unico" in restricciones
        restriccion = restricciones["detalle_conciliacion_bancaria_unico"]
        assert isinstance(restriccion, UniqueConstraint)
        assert set(restriccion.fields) == {"conciliacion", "movimiento_bancario"}

    @pytest.mark.django_db
    def test_movimiento_duplicado_en_misma_conciliacion_es_rechazado(self, grafo_conciliacion):
        """Un movimiento no puede repetirse dentro de la misma conciliación."""
        conciliacion = grafo_conciliacion["conciliacion"]
        movimiento = grafo_conciliacion["movimiento_bancario"]
        _crear_detalle_bancaria(conciliacion, movimiento)
        with pytest.raises(IntegrityError):
            _crear_detalle_bancaria(conciliacion, movimiento)

    @pytest.mark.django_db
    def test_creacion_persiste_relaciones(self, grafo_conciliacion):
        """Crear un detalle bancario persiste sus claves foráneas."""
        detalle = _crear_detalle_bancaria(
            grafo_conciliacion["conciliacion"],
            grafo_conciliacion["movimiento_bancario"],
        )
        persistido = DetalleConciliacionBancaria.objects.get(pk=detalle.pk)
        assert persistido.conciliacion_id == grafo_conciliacion["conciliacion"].pk
        assert persistido.movimiento_bancario_id == grafo_conciliacion["movimiento_bancario"].pk


# ---------------------------------------------------------------------------
# ``DetalleConciliacionInterna``
# ---------------------------------------------------------------------------


class TestDetalleConciliacionInterna:
    """Pruebas de estructura y comportamiento para ``DetalleConciliacionInterna``."""

    def test_relacion_con_conciliacion_es_obligatoria(self):
        """``DetalleConciliacionInterna`` debe apuntar a una ``Conciliacion`` obligatoria."""
        campo = DetalleConciliacionInterna._meta.get_field("conciliacion")
        assert campo.many_to_one is True
        assert campo.remote_field.model is Conciliacion
        assert campo.null is False

    def test_relacion_con_movimiento_interno_es_obligatoria(self):
        """``DetalleConciliacionInterna`` debe apuntar a un ``MovimientoInterno`` obligatorio."""
        campo = DetalleConciliacionInterna._meta.get_field("movimiento_interno")
        assert campo.many_to_one is True
        assert campo.remote_field.model is MovimientoInterno
        assert campo.null is False

    def test_par_conciliacion_movimiento_es_unico(self):
        """El par ``(conciliacion, movimiento_interno)`` es único (``UniqueConstraint``)."""
        restricciones = {
            restriccion.name: restriccion for restriccion in DetalleConciliacionInterna._meta.constraints
        }
        assert "detalle_conciliacion_interna_unico" in restricciones
        restriccion = restricciones["detalle_conciliacion_interna_unico"]
        assert isinstance(restriccion, UniqueConstraint)
        assert set(restriccion.fields) == {"conciliacion", "movimiento_interno"}

    @pytest.mark.django_db
    def test_movimiento_duplicado_en_misma_conciliacion_es_rechazado(self, grafo_conciliacion):
        """Un movimiento no puede repetirse dentro de la misma conciliación."""
        conciliacion = grafo_conciliacion["conciliacion"]
        movimiento = grafo_conciliacion["movimiento_interno"]
        _crear_detalle_interna(conciliacion, movimiento)
        with pytest.raises(IntegrityError):
            _crear_detalle_interna(conciliacion, movimiento)

    @pytest.mark.django_db
    def test_creacion_persiste_relaciones(self, grafo_conciliacion):
        """Crear un detalle interno persiste sus claves foráneas."""
        detalle = _crear_detalle_interna(
            grafo_conciliacion["conciliacion"],
            grafo_conciliacion["movimiento_interno"],
        )
        persistido = DetalleConciliacionInterna.objects.get(pk=detalle.pk)
        assert persistido.conciliacion_id == grafo_conciliacion["conciliacion"].pk
        assert persistido.movimiento_interno_id == grafo_conciliacion["movimiento_interno"].pk


# ---------------------------------------------------------------------------
# ``AjusteConciliacion``
# ---------------------------------------------------------------------------


class TestAjusteConciliacion:
    """Pruebas de estructura y comportamiento para ``AjusteConciliacion``."""

    def test_importe_es_decimal_field(self):
        """El campo ``importe`` es un ``DecimalField`` (precisión monetaria)."""
        campo = AjusteConciliacion._meta.get_field("importe")
        assert isinstance(campo, models.DecimalField)

    def test_importe_no_es_float_field(self):
        """El campo ``importe`` NO es un ``FloatField`` (evita redondeo binario)."""
        campo = AjusteConciliacion._meta.get_field("importe")
        assert not isinstance(campo, models.FloatField)

    def test_importe_tiene_precision_monetaria(self):
        """El campo ``importe`` usa la precisión acordada (19 dígitos, 8 decimales)."""
        campo = AjusteConciliacion._meta.get_field("importe")
        assert campo.max_digits == 19
        assert campo.decimal_places == 8

    def test_importe_es_obligatorio(self):
        """El campo ``importe`` no admite ``NULL`` ni valores vacíos."""
        campo = AjusteConciliacion._meta.get_field("importe")
        assert campo.null is False
        assert campo.blank is False

    def test_relacion_con_conciliacion_es_obligatoria(self):
        """``AjusteConciliacion`` debe apuntar a una ``Conciliacion`` obligatoria."""
        campo = AjusteConciliacion._meta.get_field("conciliacion")
        assert campo.many_to_one is True
        assert campo.remote_field.model is Conciliacion
        assert campo.null is False

    def test_relacion_con_concepto_ajuste_es_obligatoria(self):
        """``AjusteConciliacion`` debe apuntar a un ``ConceptoAjuste`` obligatorio."""
        campo = AjusteConciliacion._meta.get_field("concepto_ajuste")
        assert campo.many_to_one is True
        assert campo.remote_field.model is ConceptoAjuste
        assert campo.null is False

    @pytest.mark.django_db
    def test_asignar_float_al_importe_lanza_error(self, grafo_conciliacion, concepto_ajuste_factory):
        """Asignar un ``float`` al ``importe`` debe lanzar un error de tipo o de validación."""
        concepto = concepto_ajuste_factory()
        with pytest.raises((ValidationError, TypeError)):
            ajuste = AjusteConciliacion(
                importe=1500.75,
                conciliacion=grafo_conciliacion["conciliacion"],
                concepto_ajuste=concepto,
            )
            ajuste.full_clean()

    @pytest.mark.django_db
    def test_importe_decimal_es_aceptado(self, grafo_conciliacion, concepto_ajuste_factory):
        """Un ``importe`` expresado como ``decimal.Decimal`` se persiste con exactitud."""
        ajuste = _crear_ajuste(
            grafo_conciliacion["conciliacion"],
            concepto_ajuste_factory(),
            importe=Decimal("1500.75"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("1500.75")

    @pytest.mark.django_db
    def test_importe_negativo_es_aceptado(self, grafo_conciliacion, concepto_ajuste_factory):
        """Un ajuste puede ser negativo (compensa diferencias en la ecuación de suma cero)."""
        ajuste = _crear_ajuste(
            grafo_conciliacion["conciliacion"],
            concepto_ajuste_factory(),
            importe=Decimal("-25.00"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("-25.00")

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self, grafo_conciliacion, concepto_ajuste_factory):
        """Crear un ``AjusteConciliacion`` persiste importe y claves foráneas."""
        concepto = concepto_ajuste_factory()
        ajuste = _crear_ajuste(
            grafo_conciliacion["conciliacion"],
            concepto,
            importe=Decimal("-25.00"),
        )
        persistido = AjusteConciliacion.objects.get(pk=ajuste.pk)
        assert persistido.importe == Decimal("-25.00")
        assert persistido.conciliacion_id == grafo_conciliacion["conciliacion"].pk
        assert persistido.concepto_ajuste_id == concepto.pk




